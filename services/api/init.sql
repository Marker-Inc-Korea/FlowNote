CREATE DATABASE IF NOT EXISTS `flowNote`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `flowNote`;

CREATE TABLE IF NOT EXISTS user_account (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id VARCHAR(64) NOT NULL,
  login_id VARCHAR(80) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  password_salt VARCHAR(64) NOT NULL,
  password_hash CHAR(64) NOT NULL,
  status ENUM('ACTIVE', 'LOCKED', 'DISABLED') NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_account_user_id (user_id),
  UNIQUE KEY uq_user_account_login_id (login_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS role (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  role_id VARCHAR(64) NOT NULL,
  role_name VARCHAR(120) NOT NULL,
  description VARCHAR(255) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_role_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_role (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  role_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_role_user_role (user_id, role_id),
  CONSTRAINT fk_user_role_user
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_user_role_role
    FOREIGN KEY (role_id) REFERENCES role (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS login_session (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id VARCHAR(96) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  revoked_at TIMESTAMP NULL DEFAULT NULL,
  last_seen_at TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_login_session_session_id (session_id),
  KEY ix_login_session_user_id (user_id),
  KEY ix_login_session_expires_at (expires_at),
  CONSTRAINT fk_login_session_user
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notification (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  notification_id VARCHAR(80) NOT NULL,
  target_user_id BIGINT UNSIGNED NOT NULL,
  actor_user_id BIGINT UNSIGNED NULL,
  event_type VARCHAR(60) NOT NULL,
  source_type ENUM('DOCUMENT', 'JOURNAL', 'SEQUENCE', 'SYSTEM') NOT NULL DEFAULT 'SYSTEM',
  source_document_id VARCHAR(80) NULL,
  source_journal_id VARCHAR(80) NULL,
  source_sequence_item_id VARCHAR(80) NULL,
  title VARCHAR(180) NOT NULL,
  message VARCHAR(600) NOT NULL,
  read_at TIMESTAMP NULL DEFAULT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_notification_notification_id (notification_id),
  KEY ix_notification_target_read (target_user_id, read_at, created_at),
  KEY ix_notification_source (source_type, source_document_id, source_journal_id, source_sequence_item_id),
  CONSTRAINT fk_notification_target_user
    FOREIGN KEY (target_user_id) REFERENCES user_account (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_notification_actor_user
    FOREIGN KEY (actor_user_id) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_folder (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  folder_id VARCHAR(80) NOT NULL,
  parent_folder_id BIGINT UNSIGNED NULL,
  folder_name VARCHAR(160) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_document_folder_folder_id (folder_id),
  UNIQUE KEY uq_document_folder_parent_name (parent_folder_id, folder_name),
  KEY ix_document_folder_parent_order (parent_folder_id, sort_order, folder_name),
  CONSTRAINT fk_document_folder_parent
    FOREIGN KEY (parent_folder_id) REFERENCES document_folder (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_document_folder_created_by
    FOREIGN KEY (created_by) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_file (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id VARCHAR(80) NOT NULL,
  folder_id BIGINT UNSIGNED NOT NULL,
  file_name VARCHAR(220) NOT NULL,
  file_type ENUM('PDF', 'EXCEL', 'PPT', 'IMAGE', 'JOURNAL') NOT NULL,
  meta_text VARCHAR(255) NULL,
  category_path VARCHAR(255) NULL,
  current_version VARCHAR(40) NOT NULL,
  owner_id BIGINT UNSIGNED NULL,
  published_at DATETIME NOT NULL,
  security_level VARCHAR(80) NOT NULL,
  page_count INT UNSIGNED NOT NULL DEFAULT 0,
  summary VARCHAR(800) NULL,
  created_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_document_file_document_id (document_id),
  KEY ix_document_file_folder (folder_id, file_name),
  CONSTRAINT fk_document_file_folder
    FOREIGN KEY (folder_id) REFERENCES document_folder (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_document_file_owner
    FOREIGN KEY (owner_id) REFERENCES user_account (id)
    ON DELETE SET NULL,
  CONSTRAINT fk_document_file_created_by
    FOREIGN KEY (created_by) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE document_file
  MODIFY file_type ENUM('PDF', 'EXCEL', 'PPT', 'IMAGE', 'JOURNAL') NOT NULL;

CREATE TABLE IF NOT EXISTS field_journal_entry (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  journal_id VARCHAR(80) NOT NULL,
  document_file_id BIGINT UNSIGNED NOT NULL,
  memo VARCHAR(1000) NULL,
  photo_file_name VARCHAR(220) NULL,
  is_handover TINYINT(1) NOT NULL DEFAULT 0,
  handover_to VARCHAR(160) NULL,
  handover_status ENUM('NONE', 'PENDING', 'CONFIRMED') NOT NULL DEFAULT 'NONE',
  created_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_field_journal_entry_journal_id (journal_id),
  KEY ix_field_journal_entry_created_at (created_at),
  KEY ix_field_journal_entry_document (document_file_id),
  CONSTRAINT fk_field_journal_entry_document
    FOREIGN KEY (document_file_id) REFERENCES document_file (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_field_journal_entry_created_by
    FOREIGN KEY (created_by) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @add_field_journal_is_handover = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE field_journal_entry ADD COLUMN is_handover TINYINT(1) NOT NULL DEFAULT 0 AFTER photo_file_name',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'field_journal_entry'
    AND COLUMN_NAME = 'is_handover'
);
PREPARE add_field_journal_is_handover_stmt FROM @add_field_journal_is_handover;
EXECUTE add_field_journal_is_handover_stmt;
DEALLOCATE PREPARE add_field_journal_is_handover_stmt;

SET @add_field_journal_handover_to = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE field_journal_entry ADD COLUMN handover_to VARCHAR(160) NULL AFTER is_handover',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'field_journal_entry'
    AND COLUMN_NAME = 'handover_to'
);
PREPARE add_field_journal_handover_to_stmt FROM @add_field_journal_handover_to;
EXECUTE add_field_journal_handover_to_stmt;
DEALLOCATE PREPARE add_field_journal_handover_to_stmt;

SET @add_field_journal_handover_status = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE field_journal_entry ADD COLUMN handover_status ENUM(''NONE'', ''PENDING'', ''CONFIRMED'') NOT NULL DEFAULT ''NONE'' AFTER handover_to',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'field_journal_entry'
    AND COLUMN_NAME = 'handover_status'
);
PREPARE add_field_journal_handover_status_stmt FROM @add_field_journal_handover_status;
EXECUTE add_field_journal_handover_status_stmt;
DEALLOCATE PREPARE add_field_journal_handover_status_stmt;

CREATE TABLE IF NOT EXISTS field_journal_handover_read (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  field_journal_entry_id BIGINT UNSIGNED NOT NULL,
  reader_user_id BIGINT UNSIGNED NULL,
  read_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_field_journal_handover_read_entry (field_journal_entry_id, read_at),
  KEY ix_field_journal_handover_read_reader (reader_user_id, read_at),
  CONSTRAINT fk_field_journal_handover_read_entry
    FOREIGN KEY (field_journal_entry_id) REFERENCES field_journal_entry (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_field_journal_handover_read_user
    FOREIGN KEY (reader_user_id) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @drop_field_journal_handover_read_unique = (
  SELECT IF(
    COUNT(*) > 0,
    'ALTER TABLE field_journal_handover_read DROP INDEX uq_field_journal_handover_read_reader',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'field_journal_handover_read'
    AND INDEX_NAME = 'uq_field_journal_handover_read_reader'
);
PREPARE drop_field_journal_handover_read_unique_stmt FROM @drop_field_journal_handover_read_unique;
EXECUTE drop_field_journal_handover_read_unique_stmt;
DEALLOCATE PREPARE drop_field_journal_handover_read_unique_stmt;

SET @add_field_journal_handover_read_reader_index = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE field_journal_handover_read ADD KEY ix_field_journal_handover_read_reader (reader_user_id, read_at)',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'field_journal_handover_read'
    AND INDEX_NAME = 'ix_field_journal_handover_read_reader'
);
PREPARE add_field_journal_handover_read_reader_index_stmt FROM @add_field_journal_handover_read_reader_index;
EXECUTE add_field_journal_handover_read_reader_index_stmt;
DEALLOCATE PREPARE add_field_journal_handover_read_reader_index_stmt;

CREATE TABLE IF NOT EXISTS document_file_version (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_file_id BIGINT UNSIGNED NOT NULL,
  version_label VARCHAR(40) NOT NULL,
  file_name VARCHAR(220) NOT NULL,
  change_note VARCHAR(500) NOT NULL,
  owner_id BIGINT UNSIGNED NULL,
  published_at DATETIME NOT NULL,
  status ENUM('CURRENT', 'ARCHIVED') NOT NULL DEFAULT 'ARCHIVED',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_document_file_version_label (document_file_id, version_label),
  KEY ix_document_file_version_document (document_file_id, published_at),
  CONSTRAINT fk_document_file_version_file
    FOREIGN KEY (document_file_id) REFERENCES document_file (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_document_file_version_owner
    FOREIGN KEY (owner_id) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_file_storage (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_file_version_id BIGINT UNSIGNED NOT NULL,
  storage_path VARCHAR(500) NOT NULL,
  original_file_name VARCHAR(220) NOT NULL,
  mime_type VARCHAR(160) NULL,
  byte_size BIGINT UNSIGNED NOT NULL,
  sha256_hash CHAR(64) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_document_file_storage_version (document_file_version_id),
  KEY ix_document_file_storage_hash (sha256_hash),
  CONSTRAINT fk_document_file_storage_version
    FOREIGN KEY (document_file_version_id) REFERENCES document_file_version (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_editor_draft (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_file_id BIGINT UNSIGNED NOT NULL,
  editor_format VARCHAR(40) NOT NULL,
  title VARCHAR(220) NOT NULL,
  body MEDIUMTEXT NULL,
  updated_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_document_editor_draft_file (document_file_id),
  CONSTRAINT fk_document_editor_draft_file
    FOREIGN KEY (document_file_id) REFERENCES document_file (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_document_editor_draft_updated_by
    FOREIGN KEY (updated_by) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS field_journal_reply (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  reply_id VARCHAR(80) NOT NULL,
  field_journal_entry_id BIGINT UNSIGNED NOT NULL,
  document_file_version_id BIGINT UNSIGNED NULL,
  reply_text VARCHAR(1000) NOT NULL,
  reply_type ENUM('COMMENT', 'ACTION', 'QUESTION') NOT NULL DEFAULT 'COMMENT',
  created_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_field_journal_reply_reply_id (reply_id),
  KEY ix_field_journal_reply_entry (field_journal_entry_id, created_at),
  KEY ix_field_journal_reply_version (document_file_version_id),
  CONSTRAINT fk_field_journal_reply_entry
    FOREIGN KEY (field_journal_entry_id) REFERENCES field_journal_entry (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_field_journal_reply_version
    FOREIGN KEY (document_file_version_id) REFERENCES document_file_version (id)
    ON DELETE SET NULL,
  CONSTRAINT fk_field_journal_reply_created_by
    FOREIGN KEY (created_by) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE document_file d
JOIN field_journal_entry e ON e.document_file_id = d.id
SET d.file_name = CONCAT(
    CASE
      WHEN e.is_handover = 1 THEN CONCAT(
        '인수인계',
        CASE
          WHEN e.handover_to IS NOT NULL AND e.handover_to <> '' THEN CONCAT(' - ', e.handover_to)
          ELSE ''
        END
      )
      ELSE '현장작업일지'
    END,
    ' - ',
    DATE_FORMAT(d.published_at, '%Y-%m-%d %H:%i')
  )
WHERE d.file_type = 'JOURNAL'
  AND d.file_name LIKE '%.memo';

UPDATE document_file_version v
JOIN document_file d ON d.id = v.document_file_id
SET v.file_name = d.file_name
WHERE d.file_type = 'JOURNAL'
  AND v.file_name LIKE '%.memo';

CREATE TABLE IF NOT EXISTS document_tag (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tag_id VARCHAR(80) NOT NULL,
  tag_name VARCHAR(80) NOT NULL,
  created_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_document_tag_tag_id (tag_id),
  UNIQUE KEY uq_document_tag_tag_name (tag_name),
  CONSTRAINT fk_document_tag_created_by
    FOREIGN KEY (created_by) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_file_tag (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_file_id BIGINT UNSIGNED NOT NULL,
  tag_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_document_file_tag_file_tag (document_file_id, tag_id),
  KEY ix_document_file_tag_tag (tag_id),
  CONSTRAINT fk_document_file_tag_file
    FOREIGN KEY (document_file_id) REFERENCES document_file (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_document_file_tag_tag
    FOREIGN KEY (tag_id) REFERENCES document_tag (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_history (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_file_id BIGINT UNSIGNED NOT NULL,
  document_file_version_id BIGINT UNSIGNED NULL,
  event_type VARCHAR(40) NOT NULL,
  before_value JSON NULL,
  after_value JSON NULL,
  actor_user_id BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_document_history_file (document_file_id, created_at),
  KEY ix_document_history_event (event_type, created_at),
  CONSTRAINT fk_document_history_file
    FOREIGN KEY (document_file_id) REFERENCES document_file (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_document_history_version
    FOREIGN KEY (document_file_version_id) REFERENCES document_file_version (id)
    ON DELETE SET NULL,
  CONSTRAINT fk_document_history_actor
    FOREIGN KEY (actor_user_id) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS work_sequence_board (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  board_id VARCHAR(64) NOT NULL,
  board_name VARCHAR(160) NOT NULL,
  board_type ENUM('LOCAL', 'MES') NOT NULL DEFAULT 'LOCAL',
  location_name VARCHAR(120) NULL,
  is_default TINYINT(1) NOT NULL DEFAULT 0,
  created_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_work_sequence_board_board_id (board_id),
  KEY ix_work_sequence_board_is_default (is_default),
  CONSTRAINT fk_work_sequence_board_created_by
    FOREIGN KEY (created_by) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS work_sequence_item (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sequence_item_id VARCHAR(80) NOT NULL,
  board_id BIGINT UNSIGNED NOT NULL,
  sequence_no INT NOT NULL,
  title VARCHAR(180) NOT NULL,
  product_code VARCHAR(80) NULL,
  assigned_team VARCHAR(120) NULL,
  target_quantity INT UNSIGNED NULL,
  linked_document_name VARCHAR(180) NULL,
  linked_document_file_id BIGINT UNSIGNED NULL,
  status ENUM('WAITING', 'IN_PROGRESS', 'HOLD', 'DONE', 'CANCELED') NOT NULL DEFAULT 'WAITING',
  memo VARCHAR(500) NULL,
  created_by BIGINT UNSIGNED NULL,
  updated_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_work_sequence_item_item_id (sequence_item_id),
  KEY ix_work_sequence_item_board_order (board_id, status, sequence_no, id),
  KEY ix_work_sequence_item_linked_document (linked_document_file_id),
  CONSTRAINT fk_work_sequence_item_board
    FOREIGN KEY (board_id) REFERENCES work_sequence_board (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_work_sequence_item_linked_document
    FOREIGN KEY (linked_document_file_id) REFERENCES document_file (id)
    ON DELETE SET NULL,
  CONSTRAINT fk_work_sequence_item_created_by
    FOREIGN KEY (created_by) REFERENCES user_account (id)
    ON DELETE SET NULL,
  CONSTRAINT fk_work_sequence_item_updated_by
    FOREIGN KEY (updated_by) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS work_sequence_history (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sequence_item_id BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(40) NOT NULL,
  before_value JSON NULL,
  after_value JSON NULL,
  actor_user_id BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_work_sequence_history_item (sequence_item_id, created_at),
  CONSTRAINT fk_work_sequence_history_item
    FOREIGN KEY (sequence_item_id) REFERENCES work_sequence_item (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_work_sequence_history_actor
    FOREIGN KEY (actor_user_id) REFERENCES user_account (id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO role (role_id, role_name, description)
VALUES
  ('super-admin', '최고관리자', '회원 등급과 시스템 설정을 관리'),
  ('mes-user', 'MES 사용자', 'MES 연동 작업과 생산 기준정보 확인'),
  ('pop-user', 'POP 사용자', '현장 단말기에서 문서와 작업일지 사용'),
  ('general-user', '일반 사용자', '허용된 문서와 기본 화면 사용')
ON DUPLICATE KEY UPDATE
  role_name = VALUES(role_name),
  description = VALUES(description);

INSERT INTO user_account (
  user_id,
  login_id,
  display_name,
  password_salt,
  password_hash,
  status
)
VALUES
  (
    'user-admin-local',
    'admin',
    '김최고 관리자',
    'flownote-local-admin',
    SHA2(CONCAT('flownote-local-admin', '1234'), 256),
    'ACTIVE'
  ),
  (
    'user-mes-local',
    'mes',
    '박MES 사용자',
    'flownote-local-mes',
    SHA2(CONCAT('flownote-local-mes', '1234'), 256),
    'ACTIVE'
  ),
  (
    'user-pop-local',
    'pop',
    '홍POP 반장',
    'flownote-local-pop',
    SHA2(CONCAT('flownote-local-pop', '1234'), 256),
    'ACTIVE'
  ),
  (
    'user-general-local',
    'user',
    '이일반 사용자',
    'flownote-local-user',
    SHA2(CONCAT('flownote-local-user', '1234'), 256),
    'ACTIVE'
  )
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  password_salt = VALUES(password_salt),
  password_hash = VALUES(password_hash),
  status = VALUES(status);

DELETE ur
FROM user_role ur
JOIN role r ON r.id = ur.role_id
WHERE r.role_id IN ('field-user', 'document-admin', 'system-admin');

DELETE ur
FROM user_role ur
JOIN user_account u ON u.id = ur.user_id
WHERE u.login_id IN ('admin', 'mes', 'pop', 'user', 'field');

INSERT INTO user_role (user_id, role_id)
SELECT u.id, r.id
FROM user_account u
JOIN role r ON r.role_id = 'super-admin'
WHERE u.login_id = 'admin'
ON DUPLICATE KEY UPDATE user_id = VALUES(user_id);

INSERT INTO user_role (user_id, role_id)
SELECT u.id, r.id
FROM user_account u
JOIN role r ON r.role_id = 'mes-user'
WHERE u.login_id = 'mes'
ON DUPLICATE KEY UPDATE user_id = VALUES(user_id);

INSERT INTO user_role (user_id, role_id)
SELECT u.id, r.id
FROM user_account u
JOIN role r ON r.role_id = 'pop-user'
WHERE u.login_id = 'pop'
ON DUPLICATE KEY UPDATE user_id = VALUES(user_id);

INSERT INTO user_role (user_id, role_id)
SELECT u.id, r.id
FROM user_account u
JOIN role r ON r.role_id = 'pop-user'
WHERE u.login_id = 'field'
ON DUPLICATE KEY UPDATE user_id = VALUES(user_id);

INSERT INTO user_role (user_id, role_id)
SELECT u.id, r.id
FROM user_account u
JOIN role r ON r.role_id = 'general-user'
WHERE u.login_id = 'user'
ON DUPLICATE KEY UPDATE user_id = VALUES(user_id);

INSERT INTO document_folder (
  folder_id,
  parent_folder_id,
  folder_name,
  sort_order,
  created_by
)
SELECT
  'folder-my-pc',
  NULL,
  '문서함',
  10,
  u.id
FROM user_account u
WHERE u.login_id = 'admin'
ON DUPLICATE KEY UPDATE
  folder_name = VALUES(folder_name),
  sort_order = VALUES(sort_order);

INSERT INTO document_folder (
  folder_id,
  parent_folder_id,
  folder_name,
  sort_order,
  created_by
)
SELECT
  'folder-my-pc-journal',
  parent.id,
  '작업일지',
  20,
  u.id
FROM document_folder parent
JOIN user_account u ON u.login_id = 'admin'
WHERE parent.folder_id = 'folder-my-pc'
ON DUPLICATE KEY UPDATE
  parent_folder_id = VALUES(parent_folder_id),
  folder_name = VALUES(folder_name),
  sort_order = VALUES(sort_order);

INSERT INTO document_folder (
  folder_id,
  parent_folder_id,
  folder_name,
  sort_order,
  created_by
)
SELECT
  'folder-field-documents',
  parent.id,
  '현장 문서',
  10,
  u.id
FROM document_folder parent
JOIN user_account u ON u.login_id = 'admin'
WHERE parent.folder_id = 'folder-my-pc'
ON DUPLICATE KEY UPDATE
  parent_folder_id = VALUES(parent_folder_id),
  folder_name = VALUES(folder_name),
  sort_order = VALUES(sort_order);

INSERT INTO document_folder (
  folder_id,
  parent_folder_id,
  folder_name,
  sort_order,
  created_by
)
SELECT
  seeded.folder_id,
  parent.id,
  seeded.folder_name,
  seeded.sort_order,
  u.id
FROM document_folder parent
JOIN user_account u ON u.login_id = 'admin'
JOIN (
  SELECT 'folder-line-1' AS folder_id, '1호기 설비' AS folder_name, 10 AS sort_order
  UNION ALL SELECT 'folder-work-standard', '작업 표준서', 20
  UNION ALL SELECT 'folder-checklist', '점검 양식', 30
  UNION ALL SELECT 'folder-quality-records', '품질 기록', 40
  UNION ALL SELECT 'folder-project', '프로젝트', 50
) seeded
WHERE parent.folder_id = 'folder-field-documents'
ON DUPLICATE KEY UPDATE
  parent_folder_id = VALUES(parent_folder_id),
  folder_name = VALUES(folder_name),
  sort_order = VALUES(sort_order);

INSERT INTO document_folder (
  folder_id,
  parent_folder_id,
  folder_name,
  sort_order,
  created_by
)
SELECT
  seeded.folder_id,
  parent.id,
  seeded.folder_name,
  seeded.sort_order,
  u.id
FROM document_folder parent
JOIN user_account u ON u.login_id = 'admin'
JOIN (
  SELECT 'folder-cooling-system' AS folder_id, '냉각시스템' AS folder_name, 10 AS sort_order
  UNION ALL SELECT 'folder-pipe', '배관', 20
) seeded
WHERE parent.folder_id = 'folder-line-1'
ON DUPLICATE KEY UPDATE
  parent_folder_id = VALUES(parent_folder_id),
  folder_name = VALUES(folder_name),
  sort_order = VALUES(sort_order);

INSERT INTO document_file (
  document_id,
  folder_id,
  file_name,
  file_type,
  meta_text,
  category_path,
  current_version,
  owner_id,
  published_at,
  security_level,
  page_count,
  summary,
  created_by
)
SELECT
  seeded.document_id,
  folder.id,
  seeded.file_name,
  seeded.file_type,
  seeded.meta_text,
  seeded.category_path,
  seeded.current_version,
  owner.id,
  seeded.published_at,
  seeded.security_level,
  seeded.page_count,
  seeded.summary,
  admin_user.id
FROM (
  SELECT
    'doc-cooling-drawing' AS document_id,
    'folder-cooling-system' AS folder_public_id,
    'admin' AS owner_login_id,
    '1호기_도면.pdf' AS file_name,
    'PDF' AS file_type,
    '냉각시스템 / 현장 공개' AS meta_text,
    '1호기 설비 / 냉각시스템' AS category_path,
    'v3' AS current_version,
    '2026-05-22 14:10:00' AS published_at,
    '현장 공개' AS security_level,
    12 AS page_count,
    '냉각 배관, 밸브 위치, 점검 기준을 포함한 현장 열람용 도면입니다.' AS summary
  UNION ALL
  SELECT
    'doc-pipe-manual',
    'folder-pipe',
    'mes',
    '배관매뉴얼.pdf',
    'PDF',
    '1호기 설비 / v3',
    '1호기 설비 / 배관',
    'v3',
    '2026-05-20 09:30:00',
    '사내 열람',
    28,
    '배관 유지보수 절차와 주요 부품 교체 기준을 정리한 매뉴얼입니다.'
  UNION ALL
  SELECT
    'doc-checklist',
    'folder-checklist',
    'admin',
    '체크리스트.xlsx',
    'EXCEL',
    '점검 양식 / 뷰어 전용',
    '점검 양식',
    'v1',
    '2026-05-18 16:40:00',
    '뷰어 전용',
    3,
    '일일 설비 점검 항목과 확인 결과 입력 기준을 담은 문서입니다.'
) seeded
JOIN document_folder folder ON folder.folder_id = seeded.folder_public_id
JOIN user_account owner ON owner.login_id = seeded.owner_login_id
JOIN user_account admin_user ON admin_user.login_id = 'admin'
ON DUPLICATE KEY UPDATE
  folder_id = VALUES(folder_id),
  file_name = VALUES(file_name),
  file_type = VALUES(file_type),
  meta_text = VALUES(meta_text),
  category_path = VALUES(category_path),
  current_version = VALUES(current_version),
  owner_id = VALUES(owner_id),
  published_at = VALUES(published_at),
  security_level = VALUES(security_level),
  page_count = VALUES(page_count),
  summary = VALUES(summary),
  created_by = VALUES(created_by);

INSERT INTO document_file_version (
  document_file_id,
  version_label,
  file_name,
  change_note,
  owner_id,
  published_at,
  status
)
SELECT
  document_file.id,
  seeded.version_label,
  seeded.file_name,
  seeded.change_note,
  owner.id,
  seeded.published_at,
  seeded.status
FROM (
  SELECT 'doc-cooling-drawing' AS document_id, 'v3' AS version_label, '1호기_도면_v3.pdf' AS file_name, '현장 점검 기준과 밸브 위치 변경 사항 반영' AS change_note, 'admin' AS owner_login_id, '2026-05-22 14:10:00' AS published_at, 'CURRENT' AS status
  UNION ALL SELECT 'doc-cooling-drawing', 'v2', '1호기_도면_v2.pdf', '냉각 배관 라인 표기 보완', 'mes', '2026-05-12 10:20:00', 'ARCHIVED'
  UNION ALL SELECT 'doc-cooling-drawing', 'v1', '1호기_도면_v1.pdf', '최초 등록', 'admin', '2026-05-01 09:00:00', 'ARCHIVED'
  UNION ALL SELECT 'doc-pipe-manual', 'v3', '배관매뉴얼_v3.pdf', '부품 교체 주기와 작업 전 안전 확인 항목 추가', 'mes', '2026-05-20 09:30:00', 'CURRENT'
  UNION ALL SELECT 'doc-pipe-manual', 'v2', '배관매뉴얼_v2.pdf', '유지보수 절차 문구 수정', 'admin', '2026-05-08 15:15:00', 'ARCHIVED'
  UNION ALL SELECT 'doc-checklist', 'v1', '체크리스트_v1.xlsx', '최초 등록', 'admin', '2026-05-18 16:40:00', 'CURRENT'
) seeded
JOIN document_file ON document_file.document_id = seeded.document_id
JOIN user_account owner ON owner.login_id = seeded.owner_login_id
ON DUPLICATE KEY UPDATE
  file_name = VALUES(file_name),
  change_note = VALUES(change_note),
  owner_id = VALUES(owner_id),
  published_at = VALUES(published_at),
  status = VALUES(status);

INSERT INTO document_tag (
  tag_id,
  tag_name,
  created_by
)
SELECT
  CONCAT('tag-seed-', REPLACE(seeded.tag_name, ' ', '-')),
  seeded.tag_name,
  u.id
FROM user_account u
JOIN (
  SELECT '도면' AS tag_name
  UNION ALL SELECT '냉각'
  UNION ALL SELECT '배관'
  UNION ALL SELECT '설비'
  UNION ALL SELECT '현장공개'
  UNION ALL SELECT '작업표준'
  UNION ALL SELECT '점검'
  UNION ALL SELECT '양식'
) seeded
WHERE u.login_id = 'admin'
ON DUPLICATE KEY UPDATE
  tag_name = VALUES(tag_name);

INSERT INTO document_file_tag (
  document_file_id,
  tag_id
)
SELECT
  document_file.id,
  document_tag.id
FROM (
  SELECT 'doc-cooling-drawing' AS document_id, '도면' AS tag_name
  UNION ALL SELECT 'doc-cooling-drawing', '냉각'
  UNION ALL SELECT 'doc-cooling-drawing', '배관'
  UNION ALL SELECT 'doc-cooling-drawing', '설비'
  UNION ALL SELECT 'doc-cooling-drawing', '현장공개'
  UNION ALL SELECT 'doc-pipe-manual', '배관'
  UNION ALL SELECT 'doc-pipe-manual', '작업표준'
  UNION ALL SELECT 'doc-pipe-manual', '설비'
  UNION ALL SELECT 'doc-checklist', '점검'
  UNION ALL SELECT 'doc-checklist', '양식'
) seeded
JOIN document_file ON document_file.document_id = seeded.document_id
JOIN document_tag ON document_tag.tag_name = seeded.tag_name
ON DUPLICATE KEY UPDATE
  tag_id = VALUES(tag_id);

INSERT INTO work_sequence_board (
  board_id,
  board_name,
  board_type,
  location_name,
  is_default,
  created_by
)
SELECT
  'board-local-main',
  '현장 작업 순서',
  'LOCAL',
  '현장',
  1,
  u.id
FROM user_account u
WHERE u.login_id = 'admin'
ON DUPLICATE KEY UPDATE
  board_name = VALUES(board_name),
  board_type = VALUES(board_type),
  location_name = VALUES(location_name),
  is_default = VALUES(is_default);

INSERT INTO work_sequence_item (
  sequence_item_id,
  board_id,
  sequence_no,
  title,
  product_code,
  assigned_team,
  target_quantity,
  linked_document_name,
  status,
  memo,
  created_by,
  updated_by
)
SELECT
  seeded.sequence_item_id,
  b.id,
  seeded.sequence_no,
  seeded.title,
  seeded.product_code,
  seeded.assigned_team,
  seeded.target_quantity,
  seeded.linked_document_name,
  seeded.status,
  seeded.memo,
  u.id,
  u.id
FROM work_sequence_board b
JOIN user_account u ON u.login_id = 'admin'
JOIN (
  SELECT
    'seq-local-a-product' AS sequence_item_id,
    10 AS sequence_no,
    'A 제품 긴급 가공 생산' AS title,
    'A-102' AS product_code,
    '생산 1조' AS assigned_team,
    500 AS target_quantity,
    'A-102_가공도.pdf' AS linked_document_name,
    'WAITING' AS status,
    'MES 연동 전 로컬 테스트 작업' AS memo
  UNION ALL
  SELECT
    'seq-local-b-product',
    20,
    'B 제품 일반 가공 생산',
    'B-205',
    '생산 2조',
    200,
    'B-205_작업표준.pdf',
    'WAITING',
    '사무실에서 순서 조정 예정'
  UNION ALL
  SELECT
    'seq-local-c-product',
    30,
    'C 제품 대기 물량',
    'C-011',
    '대기',
    NULL,
    NULL,
    'HOLD',
    '자재 확인 후 투입'
) seeded
WHERE b.board_id = 'board-local-main'
ON DUPLICATE KEY UPDATE
  board_id = VALUES(board_id),
  sequence_no = VALUES(sequence_no),
  title = VALUES(title),
  product_code = VALUES(product_code),
  assigned_team = VALUES(assigned_team),
  target_quantity = VALUES(target_quantity),
  linked_document_name = VALUES(linked_document_name),
  status = VALUES(status),
  memo = VALUES(memo),
  updated_by = VALUES(updated_by);
