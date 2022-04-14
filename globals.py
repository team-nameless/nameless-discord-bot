from database import PostgreSqlCRUD

postgres = PostgreSqlCRUD

# DO NOT
postgres_database = postgres()
postgres_database.init()
