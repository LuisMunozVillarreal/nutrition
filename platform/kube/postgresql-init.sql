CREATE USER nutrition WITH PASSWORD '<password>';
ALTER USER nutrition CREATEDB;
\c template1;
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE DATABASE nutrition;
ALTER DATABASE nutrition OWNER TO nutrition;
