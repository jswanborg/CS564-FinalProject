import mysql.connector
import pandas as pd

# Database connection details
DB_CONFIG = {
    'host': 'vm-jgaier',
    'user': 'andrew',
    'password': 'andrew',
    'database': 'mystic_sky_mapper'
}

try:
    # Establish a connection to the MySQL database
    
    mydb = mysql.connector.connect(**DB_CONFIG)
    cursor = mydb.cursor()

    # Call the stored procedure with a parameter (e.g., limit = 100)
    cursor.callproc('getStars', (100,))

    # Fetch results from the first result set
    for result in cursor.stored_results():
        df = pd.DataFrame(result.fetchall(), columns=[desc[0] for desc in result.description])

    # Print the first few rows of the DataFrame
    print(df)

except mysql.connector.Error as err:
    print(f"Error connecting to MySQL: {err}")

finally:
    # Close the database connection if it was established
    if 'cursor' in locals():
        cursor.close()
    if 'mydb' in locals() and mydb.is_connected():
        mydb.close()
        print("MySQL connection closed.")