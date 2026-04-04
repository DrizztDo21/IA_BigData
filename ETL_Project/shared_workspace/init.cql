CREATE KEYSPACE IF NOT EXISTS ecommerce WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
USE ecommerce;

CREATE TABLE IF NOT EXISTS alertas_fraude (
    tx_id text PRIMARY KEY,
    user_id text,
    amount double,
    card_country text,
    score_fraude int,
    status text
);

CREATE TABLE IF NOT EXISTS trafico_bot (
    user_id text, 
    timestamp text,
    ip text, 
    pages_visited int,
    riesgo_historico text, 
    PRIMARY KEY ((user_id), timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC);