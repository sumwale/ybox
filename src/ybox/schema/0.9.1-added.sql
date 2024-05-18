-- records the version of the whole schema
CREATE TABLE schema (
    version TEXT NOT NULL PRIMARY KEY
) WITHOUT ROWID;

-- index on the shared_root column used in lookups
CREATE INDEX container_roots ON containers(shared_root);

-- dependencies of packages are also recorded separately to keep a proper
-- reference count and remove dependencies only if no package depends on it
CREATE TABLE package_deps (
    -- name of the package
    name TEXT NOT NULL,
    -- name of the container
    container TEXT NOT NULL,
    -- name of the dependency
    dependency TEXT NOT NULL,
    -- type of the dependency, one of "required", "optional" or "suggestion"
    -- (note that "required" dependencies are handled by underlying package manager
    --  and usually will not be recorded here)
    dep_type TEXT NOT NULL,
    PRIMARY KEY (name, container, dependency)
) WITHOUT ROWID;

-- index on package_deps for faster lookups and deletes
CREATE INDEX pkg_deps_containers ON package_deps(container);
CREATE INDEX pkg_deps_deps ON package_deps(dependency);