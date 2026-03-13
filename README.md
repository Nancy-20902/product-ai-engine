# AI-Based Product Search, Recommend & Compare

This project is an AI-powered product search and comparison system. It understands natural language queries, crawls multiple e-commerce sources, extracts product data, deduplicates similar items, ranks them using a scoring system, and displays recommendations with a comparison table.

The interface is built with Streamlit and the system uses LLMs for query understanding and explanations.

---

## Features

- Natural language product search
- Query understanding using LLM
- Multi-source crawling (Amazon, Flipkart, Brand sites, Google Shopping)
- Three-layer crawler fallback (BS4 → Crawl4AI → Playwright)
- Product extraction and normalization
- Product deduplication across sources
- Price comparison table
- Intelligent ranking and recommendations
- LLM-generated explanations
- Local knowledge base caching

---

## Architecture Overview

#### UI  
- app.py – Streamlit interface and orchestration

#### Query Understanding  
- parser.py, guardrails.py, prompts.py – NLP parsing and validation

#### LLM Interface  
- client.py – all OpenAI API calls

#### Data Models  
- schemas.py – product and query schemas

#### Crawling  
- crawler.py – crawl orchestration  
- bs4_layer.py – fast HTML scraping  
- crawl4ai_layer.py – dynamic crawling fallback  
- playwright_layer.py – stealth browser fallback  
- serper_layer.py – Google Shopping via Serper API

#### Extraction  
- extractor.py – product data extraction  
- normalizer.py – price, rating, capacity normalization

#### Matching  
- deduplicator.py – merges duplicate products

#### Ranking  
- ranker.py – scoring and recommendation labels  
- compare.py – comparison table generation

#### Storage  
- kb_manager.py – knowledge base manager  
- products.json – cached products  
- sources.json – source metadata

#### Config  
- config.py – weights and settings  
- helpers.py – utilities and logging

---

## Set Up

#### Create virtual environment
```
py -3.12 -m venv venv
```
#### Activate virtual environment
```
venv\Scripts\activate
```
#### Verify Python version
```
py --version
```
#### Install dependencies
```
pip install -r requirements.txt
```
#### Install Playwright browser
```
python -m playwright install --with-deps chromium
```
#### Setup Crawl4AI
```
crawl4ai-setup
```
#### Verify Crawl4AI installation
```
crawl4ai-doctor
```
#### Environment Variables
Create a `.env` file in the project root.
```
OPENAI_API_KEY=  
SERPER_API_KEY=
```
#### Run the Application
```
streamlit run app.py
```
---

## Example Query

best glass bowl under 500 microwave safe

The system will parse the query, crawl product sources, deduplicate results, rank products, and show recommendations with a comparison table.
