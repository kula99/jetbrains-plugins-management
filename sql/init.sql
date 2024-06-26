CREATE TABLE download_info(
    id VARCHAR(96) NOT NULL,
    version VARCHAR(64) NOT NULL,
    archive_name VARCHAR(64),
    md5 VARCHAR (32),
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archive_suffix VARCHAR(10),
    PRIMARY KEY(id, version)
);

CREATE TABLE ide_version(
    product_code VARCHAR(4) NOT NULL,
    build_version VARCHAR(32) NOT NULL,
    version VARCHAR(32),
    last_sync_status VARCHAR(1),
    last_sync_time DATETIME,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(build_version, product_code)
);

CREATE TABLE plugins_info(
    name VARCHAR(128) NOT NULL,
    id VARCHAR(96) NOT NULL,
    description TEXT,
    version VARCHAR(64) NOT NULL,
    change_notes TEXT,
    since_build VARCHAR(32),
    until_build VARCHAR(32),
    rating VARCHAR(5),
    archive_size INTEGER,
    release_time DATETIME,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tags VARCHAR (512),
    PRIMARY KEY(id, version)
);

CREATE TABLE support_version(
    id VARCHAR (96) NOT NULL,
    version VARCHAR(64) NOT NULL,
    product_code VARCHAR(4) NOT NULL,
    build_version VARCHAR(32) NOT NULL,
    latest_version INTEGER DEFAULT 1 CHECK(latest_version in (0,1)),
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(id, version, build_version, product_code)
);

CREATE TABLE support_version_history(
    id VARCHAR(96) NOT NULL,
    version VARCHAR(64) NOT NULL,
    product_code VARCHAR(4) NOT NULL,
    build_version VARCHAR(32) NOT NULL,
    latest_version INTEGER DEFAULT 0 CHECK(latest_version in (0,1)),
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, version, build_version, product_code)
);

CREATE TABLE white_list(
    plugin_id VARCHAR(96) NOT NULL,
    enabled VARCHAR(2) DEFAULT '1' NOT NULL,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(plugin_id)
);

CREATE TABLE plugins_base_info(
    name VARCHAR(128) NOT NULL,
    id VARCHAR(96) NOT NULL,
    description TEXT,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(id)
);

CREATE TABLE plugins_version_info(
    id VARCHAR(96) NOT NULL,
    version VARCHAR(64) NOT NULL,
    change_notes TEXT,
    since_build VARCHAR(32),
    until_build VARCHAR(32),
    rating VARCHAR(5),
    archive_size INTEGER,
    release_time DATETIME,
    tags VARCHAR(512),
    vendor_id VARCHAR(32),
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(id, version)
);

CREATE TABLE vendor_info(
    id VARCHAR(32) NOT NULL,
    name VARCHAR(128) NOT NULL,
    email VARCHAR(256),
    url VARCHAR(256),
    dev_type VARCHAR(10),
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(id)
);

CREATE TABLE tmp_ticket(
    ticket VARCHAR(32) NOT NULL,
    access_token VARCHAR(128) NOT NULL,
    user_name VARCHAR(64),
    step INT(2) NOT NULL DEFAULT 1,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(ticket)
);

CREATE TABLE upload_batch_info(
    batch_no VARCHAR(32) NOT NULL,
    plugin_id VARCHAR(96) NOT NULL,
    plugin_version VARCHAR(64) NOT NULL,
    archive_name VARCHAR(64),
    archive_suffix VARCHAR(10),
    since_build VARCHAR(32),
    until_build VARCHAR(32),
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(batch_no)
);

CREATE TABLE upload_chunk_info(
    batch_no VARCHAR(32) NOT NULL,
    chunk_order INT(3) NOT NULL DEFAULT 1,
    saved_path VARCHAR(128) NOT NULL,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(batch_no, chunk_order)
);

drop function if exists version_compare;
delimiter //
create
    function version_compare(version1 varchar(96), version2 varchar(96))
    returns int(1)  -- -1表示 version1 > version2，0表示相等，1表示 version1 < version2
    comment '比较版本号'
begin
    declare len1 int(3);
    declare len2 int(3);
    declare loop_times int(2) default 0;
    declare loop_count int(2) default 0;
    declare compare_result int(1) default 0;
    declare tmp_v1 varchar(32);
    declare tmp_v2 varchar(32);

    select length(version1)-length(replace(version1, '.', '')),
           length(version2)-length(replace(version2, '.', ''))
      into len1, len2;
    select LEAST(len1, len2)+1 into loop_times;

    repeat
        set loop_count = loop_count + 1;
        select SUBSTRING_INDEX(SUBSTRING_INDEX(version1, '.', loop_count), '.', -1),
               SUBSTRING_INDEX(SUBSTRING_INDEX(version2, '.', loop_count), '.', -1)
          into tmp_v1, tmp_v2;

        if tmp_v1 = '*' or tmp_v2 = '*' then
            set compare_result = 0;
        else
            select LPAD(tmp_v1, 32, '0'),
                   LPAD(tmp_v2, 32, '0')
              into tmp_v1, tmp_v2;

            if tmp_v1 = tmp_v2 then
                set compare_result = 0;
            else
                select tmp_v1 < tmp_v2 into compare_result;
                if compare_result = 0 then
                    set compare_result = -1;
                end if;
            end if;

            if loop_count = loop_times and compare_result = 0 then
                if len1 > len2 then
                    set compare_result = -1;
                elseif len1 < len2 then
                    set compare_result = 1;
                end if;
            end if;
        end if;
    until compare_result <> 0 or loop_count = loop_times
    end repeat;
    return compare_result;
end; //
delimiter ;