import numpy as np
from scipy import sparse

class PressureField:
    def __init__(
        self,
        bike_km: np.ndarray,
        radius_km: float = 1.5,
        length_scale: float = 0.8,
        alpha: float = 0.5,
        iterations: int = 3
    ):
        self.radius_km = radius_km
        self.length_scale = length_scale
        self.alpha = float(alpha)
        self.iterations = int(iterations)
        n = bike_km.shape[0]
        mask = (bike_km <= radius_km)
        dist = np.where(mask, bike_km, np.inf)
        weights = np.where(mask, np.exp(-dist / max(1e-6, length_scale)), 0.0)
        row_sums = weights.sum(axis=1, keepdims=True)
        isolated = (row_sums[:, 0] == 0)
        row_sums[isolated, 0] = 1.0
        weights[isolated, np.where(isolated)[0]] = 1.0
        normalized = weights / row_sums
        self.W = sparse.csr_matrix(normalized)

    def compute_pressure(self, signals: np.ndarray) -> np.ndarray:
        s = np.asarray(signals, dtype=float)
        if self.alpha == 0.0 or self.iterations <= 0:
            return np.clip(s, -1.0, 1.0)
        p = s.copy()
        for _ in range(self.iterations):
            p = (1.0 - self.alpha) * s + self.alpha * self.W.dot(p)
        return np.clip(p, -1.0, 1.0)
