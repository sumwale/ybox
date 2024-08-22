-- all ybox containers
CREATE TABLE containers (
    -- name of the container
    name TEXT NOT NULL PRIMARY KEY,
    -- code name for the linux distribution of the container
    distribution TEXT NOT NULL,
    -- shared root directory or empty string if not using shared root
    shared_root TEXT NOT NULL,
    -- configuration of container in INI format string
    configuration TEXT NOT NULL,
    -- if the container has been destroyed but still has packages installed in shared root
    -- then it is retained with a new unique name denoting a destroyed container
    destroyed BOOL NOT NULL
) WITHOUT ROWID;

-- all packages installed in ybox containers using ybox-pkg including dependencies
CREATE TABLE packages (
    -- name of the package
    name TEXT NOT NULL,
    -- name of the container that owns this package
    container TEXT NOT NULL,
    -- local wrappers desktop/executables created for the package (array as json)
    local_copies TEXT NOT NULL,
    -- type of local wrappers created which is a bit mask:
    --  0 for none, 1 for .desktop files, 2 for executables, 3 for both
    local_copy_type INT NOT NULL,
    -- set of flags to append to the executables when invoking from local_copies (dict as json)
    flags TEXT NOT NULL,
    PRIMARY KEY(name, container)
) WITHOUT ROWID;

-- index on the containers column used in joins and lookups
CREATE INDEX package_containers ON packages(container);

-- include the new tables and indexes added in version 0.9.1
SOURCE '0.9.1-added.sql';

-- include the new 'package_repos' table added in version 0.9.6
SOURCE '0.9.6-added.sql';
