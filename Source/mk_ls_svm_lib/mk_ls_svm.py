import numpy
import scipy
from scipy.optimize import (minimize)
from functools import reduce


class MKLSSVM:
    def __init__(self, kernel_set, C=1.0, tol=1e-4, max_iter=50):
        self.C = C
        self.tol = tol
        self.max_iter = max_iter
        self.kernel_set = kernel_set
        self.beta = numpy.array([1.0 / len(kernel_set) for _ in kernel_set])

    def fit(self, data, target, kernel_m=None):
        def kernel_matrix():
            # H_vec представляет из себя вектор матриц вычисленных ядерных функций
            # взвешенная сумма этих матриц дает искомую матрицу ядер
            # значение ядер не поменяется на протяжении всего алгоритма
            # будут меняться только веса
            trainSeqLen = len(target)
            H_vec = []
            for K in self.kernel_set:
                H = numpy.matrix(numpy.zeros(shape=(trainSeqLen, trainSeqLen)))
                for i in range(trainSeqLen):
                    for j in range(i, trainSeqLen):
                        val = K.compute(data[i], data[j])
                        H[i, j] = val
                        H[j, i] = val
                H_vec.append(H)
            return H_vec

        def kernel_matrix_y():
            Ky_vec = []
            for H in self.__Hvec:
                Ky = []
                for i, _ in enumerate(H):
                    Ky.append(numpy.asarray([y * H[i, j] for j, y in enumerate(target)], dtype=float))
                Ky_vec.append(Ky)
            return Ky_vec

        # Large Scale Algorithm
        def lagrange_coefficient_estimation():
            trainSeqLen = len(target)
            weighted_H = map(lambda h, beta: h * beta, self.__Hvec, self.beta)
            H = reduce(lambda p_h, h: p_h + h, weighted_H)
            for i in range(trainSeqLen):
                for j in range(i, trainSeqLen):
                    H[i, j] *= target[i] * target[j]
                    H[j, i] *= target[j] * target[i]
                    if i == j:
                        H[i, j] += 1.0 / self.C

            d = numpy.ones(trainSeqLen)
            eta = scipy.sparse.linalg.cg(H, target, maxiter=1000)[0]
            nu = scipy.sparse.linalg.cg(H, d, maxiter=1000)[0]
            s = numpy.dot(target.T, eta)
            b = numpy.dot(eta.T, d) / s
            alpha = nu - eta * b
            return b, alpha

        def kernel_coefficient_estimation():
            def score_func(beta_vec):
                def K_sum(i):
                    weighted_kernels = [b_c * K[i] for b_c, K in zip(beta_vec, self.__Kyvec)]
                    return numpy.array(reduce(lambda l, m: l + m, weighted_kernels))

                loss_func_vec = []
                for i, y in enumerate(target):
                    weighted_kernels_sum = K_sum(i)
                    loss_func_vec.append(1.0 - y * self.b - y * numpy.dot(weighted_kernels_sum, self.alpha))

                loss_func = reduce(lambda e1, e2: e1 + e2 ** 2, loss_func_vec)
                return loss_func

            cons = ({'type': 'eq', 'fun': lambda x: sum(x) - 1.0})
            bnds = [(0.0, 1.0) for _ in self.beta]
            betaopt = minimize(score_func, self.beta,
                               bounds=bnds, constraints=cons,
                               method='SLSQP',
                               options={'maxiter':1000, 'disp':False})

            return betaopt.x, betaopt.fun

        classes = numpy.unique(target)
        if len(classes) == 1 or len(classes) != 2:
            raise Exception('The number of classes has to be equal two')

        self.class_dict = {
            '1.0': classes[0],
            '-1.0': classes[1]}
        target = numpy.array(list(map(lambda y: 1.0 if y == classes[0] else -1.0, target)))

        self.__Xfit = data
        self.__Yfit = target

        if kernel_m is None:
            self.__Hvec = kernel_matrix()
        else:
            self.__Hvec = kernel_m

        self.__Kyvec = kernel_matrix_y()

        prev_score_value = 0
        prev_beta_norm = numpy.linalg.norm(self.beta)
        cur_iter = 0
        while True:
            self.b, self.alpha = lagrange_coefficient_estimation()
            if len(self.kernel_set) == 1:
                break
            self.beta, score_value = kernel_coefficient_estimation()
            # выход по количеству итераций
            if cur_iter >= self.max_iter:
                break
            # выход по невязке функции
            if abs(prev_score_value - score_value) < self.tol:
                break
            # выход по невязке нормы коэфициентов
            beta_norm = numpy.linalg.norm(self.beta)
            if abs(prev_beta_norm - beta_norm) < self.tol:
                break
            prev_score_value = score_value
            prev_beta_norm = beta_norm
            cur_iter += 1

        return self

    def predict(self, data):
        def y_prediction(z):
            support_vectors_sum =\
                sum([alpha * y *
                     sum([beta * K.compute(z, x) for beta, K in zip(self.beta, self.kernel_set)])
                     for alpha, x, y in zip(self.alpha, self.__Xfit, self.__Yfit)])

            p = support_vectors_sum + self.b
            if p == 0.0:
                p = 1.0;
            return self.class_dict[str(numpy.sign(p))]

        return [y_prediction(test_x) for test_x in data]
