#!/usr/bin/env python3

import sys
import numpy as np
import json

def print_help():
    print("Usage: mmx_matrix_inverse.py '[ [row1], [row2], ... ]'")
    print("Example: mmx_matrix_inverse.py '[[4,7],[2,6]]'")
    sys.exit(1)

def main():
    if len(sys.argv) != 2:
        print_help()

    try:
        # Parse matrix from argument
        matrix_str = sys.argv[1]
        matrix = np.array(json.loads(matrix_str), dtype=float)

        if matrix.shape[0] != matrix.shape[1]:
            print("❌ Error: Matrix must be square (n x n)")
            sys.exit(2)

        # Check invertibility
        det = np.linalg.det(matrix)
        if det == 0:
            print("❌ Error: Matrix is singular (non-invertible)")
            sys.exit(3)

        # Invert
        inverse = np.linalg.inv(matrix)
        print("✅ Inverse Matrix:")
        print(inverse)

        # Verify
        identity = np.dot(matrix, inverse)
        print("\n✅ Verification (A · A⁻¹ = I):")
        print(identity)

    except Exception as e:
        print(f"❌ Exception: {e}")
        sys.exit(4)

if __name__ == "__main__":
    main()
