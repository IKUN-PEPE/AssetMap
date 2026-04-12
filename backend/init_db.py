from app.tasks.bootstrap import create_all_tables


if __name__ == "__main__":
    create_all_tables()
    print("Database tables created.")
