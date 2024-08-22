-- add the destroyed column to containers
ALTER TABLE containers ADD COLUMN destroyed BOOL NOT NULL DEFAULT false;

-- move the entries from "destroyed_containers" to containers with destroyed column as true
INSERT OR IGNORE INTO containers SELECT name, distribution, shared_root, configuration, true
FROM destroyed_containers;

DROP TABLE destroyed_containers;
