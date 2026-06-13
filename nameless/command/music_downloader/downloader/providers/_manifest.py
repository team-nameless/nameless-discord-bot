from typing import Any, NotRequired, TypedDict


class QualityOptionManifest(TypedDict):
    id: str
    label: str
    description: str


class ServiceHealthManifest(TypedDict):
    id: str
    label: str
    url: str
    method: str
    serviceKey: str
    timeoutMs: int
    cacheTtlSeconds: int
    required: bool


class ProviderSettingsManifest(TypedDict):
    key: str
    label: str
    type: str
    default: Any
    description: str
    secret: NotRequired[bool]
    options: NotRequired[list[str]]


class ProviderPermissionsManifest(TypedDict):
    network: NotRequired[list[str]]
    allowHttp: NotRequired[bool]
    storage: NotRequired[bool]
    file: NotRequired[bool]


class ProviderCapabilitiesManifest(TypedDict):
    downloadFallbackTier: NotRequired[str]
    downloadOutputExtension: NotRequired[str]
    requiresNativeContainerConversion: NotRequired[bool]
    replacesBuiltInProviders: NotRequired[list[str]]
    shareUrlTemplates: NotRequired[dict[str, str]]
    homeFeed: NotRequired[bool]
    browseCategories: NotRequired[bool]


class SearchFilterManifest(TypedDict):
    id: str
    label: str
    icon: NotRequired[str]


class SearchBehaviorManifest(TypedDict):
    enabled: bool
    primary: NotRequired[bool]
    placeholder: NotRequired[str]
    icon: NotRequired[str]
    thumbnailRatio: NotRequired[str]
    filters: NotRequired[list[SearchFilterManifest]]


class UrlHandlerManifest(TypedDict):
    enabled: bool
    patterns: list[str]


class ProviderManifest(TypedDict):
    name: str
    displayName: str
    version: str
    description: str
    homepage: NotRequired[str]
    type: list[str]
    icon: NotRequired[str]
    minAppVersion: str
    skipLyrics: NotRequired[bool]
    skipMetadataEnrichment: NotRequired[bool]
    permissions: NotRequired[ProviderPermissionsManifest]
    qualityOptions: NotRequired[list[QualityOptionManifest]]
    capabilities: NotRequired[ProviderCapabilitiesManifest]
    searchBehavior: NotRequired[SearchBehaviorManifest]
    urlHandler: NotRequired[UrlHandlerManifest]
    serviceHealth: NotRequired[list[ServiceHealthManifest]]
    settings: NotRequired[list[ProviderSettingsManifest]]

