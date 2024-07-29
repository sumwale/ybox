-- additional package repositories that have been added are tracked display them
-- and to enable removing the signing key if required
CREATE TABLE package_repos (
    -- name of the repository
    name TEXT NOT NULL,
    -- name of the container, or shared root directory (if the container is using a shared root)
    -- where the repository is being added
    container_or_shared_root TEXT NOT NULL,
    -- server URL(s) that are comma separated if multiple of them
    urls TEXT NOT NULL,
    -- key used for verifying the packages by the package manager
    key TEXT NOT NULL,
    -- additional options for the repository
    options TEXT NOT NULL,
    -- if source code repository has also been enabled
    with_source_repo BOOL NOT NULL,
    PRIMARY KEY (name, container_or_shared_root)
) WITHOUT ROWID;