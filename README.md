# Dragon Course Bot

- Run the `scrape_data.py` script in the `data` directory using the following command to scrape all the data from the course catalog

```sh 
python3 data\scrape_catalog.py
```

- Run the `create_db.py` script using the following command to load the data to Neo4j and create the relationships. Ensure that you have the appropriate credentials and environment variables setup for Neo4j and OpenAI before running this script

```sh 
python3 create_db.py
```

- You can run the main app by running the following command 
```sh 
python3 main.py
```