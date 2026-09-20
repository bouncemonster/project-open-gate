"""V5 Detector: Nearest-centroid + linear discriminant classifier."""
import math
from typing import List, Dict, Tuple, Optional


# ============================================================================
# FEATURE NORMALIZATION
# ============================================================================

class FeatureNormalizer:
    """Z-score normalization per feature."""
    
    def __init__(self):
        self.means = {}
        self.stds = {}
        self.fitted = False
    
    def fit(self, feature_vectors: List[Dict[str, float]]):
        """Fit normalizer on training data."""
        if not feature_vectors:
            return
        
        keys = feature_vectors[0].keys()
        for k in keys:
            values = [fv[k] for fv in feature_vectors if k in fv]
            n = len(values)
            if n == 0:
                self.means[k] = 0
                self.stds[k] = 1
                continue
            mean = sum(values) / n
            var = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0
            std = math.sqrt(var) if var > 0 else 1.0
            self.means[k] = mean
            self.stds[k] = std if std > 1e-10 else 1.0
        
        self.fitted = True
    
    def transform(self, fv: Dict[str, float]) -> Dict[str, float]:
        """Normalize a feature vector."""
        if not self.fitted:
            raise RuntimeError("Normalizer not fitted")
        result = {}
        for k, v in fv.items():
            if k in self.means:
                result[k] = (v - self.means[k]) / self.stds[k]
            else:
                result[k] = 0.0
        return result
    
    def fit_transform(self, feature_vectors: List[Dict[str, float]]) -> List[Dict[str, float]]:
        """Fit and transform."""
        self.fit(feature_vectors)
        return [self.transform(fv) for fv in feature_vectors]


# ============================================================================
# NEAREST CENTROID CLASSIFIER
# ============================================================================

class NearestCentroidClassifier:
    """Nearest centroid classifier with k-nearest centroids voting."""
    
    def __init__(self, k: int = 5):
        self.k = k
        self.centroids = {}  # class_label -> centroid vector
        self.classes = []
        self.fitted = False
    
    def _compute_centroid(self, vectors: List[Dict[str, float]]) -> Dict[str, float]:
        """Compute mean vector."""
        if not vectors:
            return {}
        keys = vectors[0].keys()
        centroid = {}
        for k in keys:
            values = [v[k] for v in vectors if k in v]
            centroid[k] = sum(values) / len(values) if values else 0
        return centroid
    
    def _euclidean_distance(self, a: Dict[str, float], b: Dict[str, float]) -> float:
        """Compute Euclidean distance between two vectors."""
        keys = set(a.keys()) | set(b.keys())
        return math.sqrt(sum((a.get(k, 0) - b.get(k, 0)) ** 2 for k in keys))
    
    def fit(self, feature_vectors: List[Dict[str, float]], labels: List[str]):
        """Fit classifier on training data."""
        # Group by class
        class_vectors = {}
        for fv, label in zip(feature_vectors, labels):
            if label not in class_vectors:
                class_vectors[label] = []
            class_vectors[label].append(fv)
        
        # Compute centroids
        self.classes = sorted(class_vectors.keys())
        for cls in self.classes:
            self.centroids[cls] = self._compute_centroid(class_vectors[cls])
        
        self.fitted = True
    
    def predict(self, fv: Dict[str, float]) -> str:
        """Predict class for a feature vector."""
        if not self.fitted:
            raise RuntimeError("Classifier not fitted")
        
        # Compute distances to all centroids
        distances = []
        for cls in self.classes:
            d = self._euclidean_distance(fv, self.centroids[cls])
            distances.append((d, cls))
        
        # Sort by distance
        distances.sort()
        
        # Return closest centroid
        return distances[0][1]
    
    def predict_proba(self, fv: Dict[str, float]) -> Dict[str, float]:
        """Predict class probabilities using inverse distance."""
        if not self.fitted:
            raise RuntimeError("Classifier not fitted")
        
        distances = []
        for cls in self.classes:
            d = self._euclidean_distance(fv, self.centroids[cls])
            distances.append((d, cls))
        
        distances.sort()
        
        # Convert distances to probabilities using softmax-like approach
        # Use inverse distance with temperature
        inv_dists = []
        for d, cls in distances:
            inv_d = 1.0 / (d + 1e-10)
            inv_dists.append((inv_d, cls))
        
        total = sum(id for id, _ in inv_dists)
        proba = {cls: id / total for id, cls in inv_dists}
        return proba


# ============================================================================
# LINEAR DISCRIMINANT ANALYSIS (manual implementation)
# ============================================================================

class LinearDiscriminant:
    """One-vs-rest linear discriminant (manual implementation, no sklearn)."""
    
    def __init__(self, n_components: int = 10):
        self.n_components = n_components
        self.weights = {}  # class -> weight vector
        self.biases = {}   # class -> bias
        self.classes = []
        self.fitted = False
    
    def _dot(self, a: Dict[str, float], b: Dict[str, float]) -> float:
        """Dot product of two vectors."""
        keys = set(a.keys()) & set(b.keys())
        return sum(a[k] * b[k] for k in keys)
    
    def fit(self, feature_vectors: List[Dict[str, float]], labels: List[str]):
        """Fit LDA using Fisher's criterion approximation."""
        # Group by class
        class_vectors = {}
        for fv, label in zip(feature_vectors, labels):
            if label not in class_vectors:
                class_vectors[label] = []
            class_vectors[label].append(fv)
        
        self.classes = sorted(class_vectors.keys())
        
        # Compute global mean
        all_keys = set()
        for fv in feature_vectors:
            all_keys.update(fv.keys())
        
        global_mean = {}
        for k in all_keys:
            values = [fv.get(k, 0) for fv in feature_vectors]
            global_mean[k] = sum(values) / len(values) if values else 0
        
        # For each class, compute weight vector as (mean_class - mean_rest)
        for cls in self.classes:
            cls_vectors = class_vectors[cls]
            rest_vectors = [fv for fv, l in zip(feature_vectors, labels) if l != cls]
            
            # Class mean
            cls_mean = {}
            for k in all_keys:
                values = [fv.get(k, 0) for fv in cls_vectors]
                cls_mean[k] = sum(values) / len(values) if values else 0
            
            # Rest mean
            rest_mean = {}
            for k in all_keys:
                values = [fv.get(k, 0) for fv in rest_vectors]
                rest_mean[k] = sum(values) / len(values) if values else 0
            
            # Weight = difference of means (simplified Fisher criterion)
            self.weights[cls] = {k: cls_mean.get(k, 0) - rest_mean.get(k, 0) for k in all_keys}
            
            # Bias = midpoint
            self.biases[cls] = -0.5 * self._dot(self.weights[cls], 
                                                  {k: cls_mean.get(k, 0) + rest_mean.get(k, 0) for k in all_keys})
        
        self.fitted = True
    
    def predict(self, fv: Dict[str, float]) -> str:
        """Predict class."""
        if not self.fitted:
            raise RuntimeError("LDA not fitted")
        
        scores = {}
        for cls in self.classes:
            scores[cls] = self._dot(fv, self.weights[cls]) + self.biases[cls]
        
        return max(scores, key=scores.get)
    
    def predict_proba(self, fv: Dict[str, float]) -> Dict[str, float]:
        """Predict class probabilities using softmax."""
        if not self.fitted:
            raise RuntimeError("LDA not fitted")
        
        scores = {}
        for cls in self.classes:
            scores[cls] = self._dot(fv, self.weights[cls]) + self.biases[cls]
        
        # Softmax
        max_score = max(scores.values())
        exp_scores = {cls: math.exp(s - max_score) for cls, s in scores.items()}
        total = sum(exp_scores.values())
        return {cls: v / total for cls, v in exp_scores.items()}


# ============================================================================
# COMBINED DETECTOR
# ============================================================================

class V5Detector:
    """Combined nearest-centroid + LDA detector."""
    
    def __init__(self):
        self.normalizer = FeatureNormalizer()
        self.nc_classifier = NearestCentroidClassifier(k=5)
        self.lda_classifier = LinearDiscriminant(n_components=10)
        self.fitted = False
        self.frozen = False  # For blind evaluation
    
    def fit(self, feature_vectors: List[Dict[str, float]], labels: List[str]):
        """Fit detector on training data."""
        if self.frozen:
            raise RuntimeError("Detector is frozen for blind evaluation")
        
        # Normalize features
        normalized = self.normalizer.fit_transform(feature_vectors)
        
        # Fit classifiers
        self.nc_classifier.fit(normalized, labels)
        self.lda_classifier.fit(normalized, labels)
        
        self.fitted = True
    
    def predict(self, fv: Dict[str, float]) -> str:
        """Predict using combined detector (majority vote)."""
        if not self.fitted:
            raise RuntimeError("Detector not fitted")
        
        normalized = self.normalizer.transform(fv)
        
        nc_pred = self.nc_classifier.predict(normalized)
        lda_pred = self.lda_classifier.predict(normalized)
        
        # Majority vote (if they disagree, prefer LDA as it's more discriminative)
        if nc_pred == lda_pred:
            return nc_pred
        return lda_pred
    
    def predict_proba(self, fv: Dict[str, float]) -> Dict[str, float]:
        """Predict probabilities (average of NC and LDA)."""
        if not self.fitted:
            raise RuntimeError("Detector not fitted")
        
        normalized = self.normalizer.transform(fv)
        
        nc_proba = self.nc_classifier.predict_proba(normalized)
        lda_proba = self.lda_classifier.predict_proba(normalized)
        
        # Average probabilities
        all_classes = set(nc_proba.keys()) | set(lda_proba.keys())
        combined = {}
        for cls in all_classes:
            combined[cls] = (nc_proba.get(cls, 0) + lda_proba.get(cls, 0)) / 2
        
        return combined
    
    def freeze(self):
        """Freeze detector for blind evaluation."""
        self.frozen = True
    
    def unfreeze(self):
        """Unfreeze detector."""
        self.frozen = False
    
    def is_computational(self, fv: Dict[str, float]) -> Tuple[str, float]:
        """Determine if world is computational-like or natural-like."""
        proba = self.predict_proba(fv)
        
        # Group classes by category
        computational_classes = [c for c in proba.keys() 
                                if any(x in c for x in ["W09", "W10", "W11", "W12", "W13", "W14", "W15", "W16", "W17"])]
        continuous_classes = [c for c in proba.keys() 
                             if any(x in c for x in ["W01", "W02", "W03"])]
        
        comp_prob = sum(proba.get(c, 0) for c in computational_classes)
        cont_prob = sum(proba.get(c, 0) for c in continuous_classes)
        
        if comp_prob > cont_prob:
            return "computational-like", comp_prob
        else:
            return "natural-like", cont_prob
