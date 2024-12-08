### Database Setup

1. **Install Docker**: Ensure you have docker installed on your machine.
2. **Configure `.env` file**: Create a `.env` file with the following variables:

   ```plaintext
   POSTGRES_DB=your_database_name
   POSTGRES_USER=your_db_user
   POSTGRES_PASSWORD=your_db_password
3. **Give Permission to run the script**: Ensure you give permission in order to run the script
```bash
    chmod +x ./db_setup.sh
```

4. **Run the script**: run the following script
```bash
    ./db_setup.sh
```