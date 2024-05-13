-- add the flags column to packages
ALTER TABLE packages ADD COLUMN flags TEXT NOT NULL DEFAULT '{}';
