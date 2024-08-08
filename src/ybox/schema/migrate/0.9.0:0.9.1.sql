-- first create the new tables and index

SOURCE '../0.9.1-added.sql';

-- add the destroyed_containers table
CREATE TABLE destroyed_containers (
    name TEXT NOT NULL PRIMARY KEY,
    distribution TEXT NOT NULL,
    shared_root TEXT NOT NULL,
    configuration TEXT NOT NULL
) WITHOUT ROWID;

-- delete the orphan packages having empty container fields since it is not possible to create
-- corresponding entries in destroyed_containers due to lack of container configuration information
DELETE FROM packages WHERE container = '';

-- change comma-separated local_copies field to json
UPDATE packages SET local_copies = JSON_FROM_CSV(local_copies);

-- make entries into package_deps reading from packages.type
INSERT INTO package_deps
  SELECT RTRIM(SUBSTR(type, 10), ')'), container, name, 'optional'
  FROM packages
  WHERE type LIKE 'optional(%)';

-- drop the packages.shared_root and packages.type columns
ALTER TABLE packages DROP COLUMN type;
ALTER TABLE packages DROP COLUMN shared_root;

-- add the local_copy_type column and fill it up guessing from local_copies
ALTER TABLE packages ADD COLUMN local_copy_type INT NOT NULL DEFAULT 0;
UPDATE packages SET local_copy_type = (
  CASE WHEN local_copies LIKE '%.desktop%,%bin/%' THEN 3
       WHEN local_copies LIKE '%bin/%,%.desktop%' THEN 3
       WHEN local_copies LIKE '%.desktop%' THEN 1
       WHEN local_copies LIKE '%bin/%' THEN 2
       ELSE 0
  END
);

-- add version entry, since code assumes that a valid entry will be present in the schema table
INSERT INTO schema VALUES ('0.9.1');
