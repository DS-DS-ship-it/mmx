# mmx_core/math/matrix_inversion.py

import numpy as np

__all__ = [
    "invert_matrix",
    "invert_gauss_jordan",
    "invert_lu",
    "invert_qr",
    "invert_svd"
]

def invert_matrix(A, method="auto"):
    """
    Invert a square matrix using the specified method.
    
    Parameters:
        A (ndarray): Square matrix to invert.
        method (str): 'auto', 'gauss', 'lu', 'qr', 'svd'
    
    Returns:
        A_inv (ndarray): Inverse of matrix A
    """
    if method == "auto":
        method = "lu" if np.linalg.det(A) != 0 else "svd"

    if method == "gauss":
        return invert_gauss_jordan(A)
    elif method == "lu":
        return invert_lu(A)
    elif method == "qr":
        return invert_qr(A)
    elif method == "svd":
        return invert_svd(A)
    else:
        raise ValueError(f"Unknown method: {method}")


def invert_gauss_jordan(A):
    """Invert matrix using Gauss-Jordan elimination."""
    A = np.array(A, dtype=float)
    n = A.shape[0]
    I = np.identity(n)
    AI = np.hstack([A, I])

    for i in range(n):
        # Pivoting
        max_row = np.argmax(np.abs(AI[i:, i])) + i
        AI[[i, max_row]] = AI[[max_row, i]]

        # Normalize row
        AI[i] /= AI[i, i]

        # Eliminate other rows
        for j in range(n):
            if i != j:
                AI[j] -= AI[i] * AI[j, i]

    return AI[:, n:]


def invert_lu(A):
    """Invert matrix using LU decomposition."""
    from scipy.linalg import lu_factor, lu_solve
    lu, piv = lu_factor(A)
    I = np.identity(A.shape[0])
    return lu_solve((lu, piv), I)


def invert_qr(A):
    """Invert matrix using QR decomposition."""
    Q, R = np.linalg.qr(A)
    return np.linalg.inv(R) @ Q.T


def invert_svd(A):
    """Invert matrix using SVD (robust for near-singular matrices)."""
    U, S, Vt = np.linalg.svd(A)
    S_inv = np.diag([1/s if s > 1e-10 else 0 for s in S])
    return Vt.T @ S_inv @ U.T
