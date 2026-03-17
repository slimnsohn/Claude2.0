import pickle
from pathlib import Path
import pandas as pd
from sdv.metadata import SingleTableMetadata
from sdv.single_table import GaussianCopulaSynthesizer


class ModelTrainer:
    """Trains and manages SDV synthesizer models."""

    def __init__(self):
        self.model = None
        self.metadata = None

    def fit(self, data: pd.DataFrame, categorical_columns: list[str] = None,
            numerical_columns: list[str] = None) -> None:
        """Fit a GaussianCopulaSynthesizer on the data."""
        self.metadata = SingleTableMetadata()
        self.metadata.detect_from_dataframe(data)

        # Override detected types if specified
        if categorical_columns:
            for col in categorical_columns:
                if col in data.columns:
                    self.metadata.update_column(col, sdtype='categorical')
        if numerical_columns:
            for col in numerical_columns:
                if col in data.columns:
                    self.metadata.update_column(col, sdtype='numerical')

        self.model = GaussianCopulaSynthesizer(self.metadata)
        self.model.fit(data)

    def save(self, path: str) -> None:
        """Save fitted model to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump({'model': self.model, 'metadata': self.metadata}, f)

    def load(self, path: str) -> None:
        """Load model from disk."""
        with open(path, 'rb') as f:
            data = pickle.load(f)
            self.model = data['model']
            self.metadata = data['metadata']

    def generate(self, n: int) -> pd.DataFrame:
        """Generate n synthetic samples from the fitted model."""
        if self.model is None:
            raise RuntimeError("Model not fitted or loaded")
        return self.model.sample(num_rows=n)
