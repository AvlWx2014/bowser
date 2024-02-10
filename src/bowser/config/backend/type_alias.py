from .aws import AwsS3BowserBackendConfig


# as more backend config types are added, expand this as a union of types
# e.g. AwsS3BowserBackendConfig | AwsEFSBowserBackendConfig | SomeOtherBackendConfig
BowserBackendConfigT = AwsS3BowserBackendConfig
