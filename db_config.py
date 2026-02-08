import os

db_config = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', 'Test@123'),
    'database': os.getenv('MYSQL_DATABASE', 'mydata'),
    'port': int(os.getenv('MYSQL_PORT', 3306))
}
