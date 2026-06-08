CREATE DATABASE IF NOT EXISTS freecadai
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'freecadai'@'%' IDENTIFIED BY 'freecadai_password';
GRANT ALL PRIVILEGES ON freecadai.* TO 'freecadai'@'%';
FLUSH PRIVILEGES;
