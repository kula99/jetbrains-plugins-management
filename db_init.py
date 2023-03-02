import sqlite3

conn = sqlite3.connect('plugins.db')
cur = conn.cursor()
cur.executescript('''
CREATE TABLE download_info(
    id TEXT NOT NULL,
    version TEXT NOT NULL,
    archive_name TEXT,
    md5 TEXT,
    create_time TEXT default (datetime('now', 'localtime')),
    update_time TEXT default (datetime('now', 'localtime')),
    PRIMARY KEY(id, version));


CREATE TABLE ide_version(
    product_code TEXT NOT NULL,
    build_version TEXT NOT NULL, 
    version TEXT,
    UNIQUE(product_code, build_version)
);


CREATE TABLE plugins_info(
    name TEXT NOT NULL,
    id TEXT NOT NULL,
    description TEXT,
    version TEXT NOT NULL,
    change_notes TEXT,
    since_build TEXT,
    until_build TEXT,
    rating TEXT,
    archive_size INTEGER,
    release_time TEXT,
    create_time TEXT default (datetime('now', 'localtime')),
    update_time TEXT default (datetime('now', 'localtime')),
    PRIMARY KEY(id, version));


CREATE TABLE support_version(
    id TEXT NOT NULL,
    version TEXT NOT NULL,	
    product_code TEXT NOT NULL,
    build_version TEXT NOT NULL,
    latest_version INTEGER default 1 check(latest_version in (0,1)),
    create_time TEXT default (datetime('now', 'localtime')),
    update_time TEXT default (datetime('now', 'localtime')),
    UNIQUE(id, version, product_code, build_version));


CREATE TABLE white_list(
    plugin_id TEXT NOT NULL unique
);

ALTER TABLE plugins_info ADD COLUMN tags text;
''')


conn.commit()
conn.close()
