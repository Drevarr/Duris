-- One bit per first-find tip a character has already been shown.
-- Existing characters take the all-seen default; the server saves zero for new ones.
SET @first_find_tips_sql = IF(EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='player_data'
      AND column_name='first_find_tips'),
    'SELECT 1',
    'ALTER TABLE player_data ADD COLUMN first_find_tips BIGINT UNSIGNED NOT NULL DEFAULT 18446744073709551615');
PREPARE first_find_tips_stmt FROM @first_find_tips_sql;
EXECUTE first_find_tips_stmt;
DEALLOCATE PREPARE first_find_tips_stmt;
