"""Provider identity definitions for embedding providers."""

class EmbeddingProviderIdentity:
    def __init__(self, name: str, model: str, version: str, dimension: int):
        self.name = name
        self.model = model
        self.version = version
        self.dimension = dimension

    def __eq__(self, other):
        if not isinstance(other, EmbeddingProviderIdentity):
            return False
        return (self.name == other.name and
                self.model == other.model and
                self.version == other.version and
                self.dimension == other.dimension)

    def __repr__(self):
        return f"EmbeddingProviderIdentity(name={self.name}, model={self.model}, version={self.version}, dimension={self.dimension})"


# Predefined provider identities
MOCK_IDENTITY = EmbeddingProviderIdentity(
    name="mock",
    model="mock",
    version="0.1.0",
    dimension=384
)

NVIDIA_IDENTITY = EmbeddingProviderIdentity(
    name="nvidia",
    model="nvidia/nemotron-3-embed-1b",
    version="1.0.0",
    dimension=2048
)

# Map from provider name to identity
PROVIDER_IDENTITIES = {
    "mock": MOCK_IDENTITY,
    "nvidia": NVIDIA_IDENTITY,
}


def get_provider_identity(provider_name: str) -> EmbeddingProviderIdentity:
    """
    Get the identity for a given provider name.
    Raises KeyError if provider is unknown.
    """
    return PROVIDER_IDENTITIES[provider_name]


def get_provider_identity_or_default(provider_name: str, default: EmbeddingProviderIdentity = MOCK_IDENTITY) -> EmbeddingProviderIdentity:
    """
    Get the identity for a given provider name, returning default if unknown.
    """
    return PROVIDER_IDENTITIES.get(provider_name, default)
