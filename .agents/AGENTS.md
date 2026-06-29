# AGENTS.md - Backend Guide

This document is designed to provide context and guidance for any AI agent or developer interacting with the `backendGossipGarden` repository. It provides an analysis of the structure, the general context of its functions, and rules for extending, refactoring, or migrating code.

## 1. Architectural Structure

The backend is a **FastAPI** application relying on a polyglot persistence strategy:
- **Supabase (PostgreSQL)**: Primary relational store and pgvector (RAG) backend.
- **Firebase Firestore**: Telemetry, chat logs, JSON metadata.
- **Firebase Storage**: Image hosting.
- **Redis**: Fast, short-term and medium-term caching.

### Directory Breakdown
- **`app/main.py`**: The main entry point. Handles the app lifecycle (`lifespan`), validating DB connections, and starting MQTT if enabled.
- **`app/api/v1/`**: The HTTP routing layer. Contains endpoints grouped by domain (`plants`, `auth`, `sensors`, `chat`, `identification`). Handlers here should be kept thin.
- **`app/services/`**: The core business logic layer. All heavy lifting, third-party API interactions (e.g., OpenAI, plant.id, GBIF), and complex database operations reside here.
- **`app/schemas/`**: Pydantic v2 data models for request validation and response formatting.
- **`app/core/`**: Core utilities, including configuration (`config.py`), security (`security.py`), and background tasks like MQTT (`mqtt.py`).
- **`app/db/`**: Database client initializations (Singletons). Never import these directly into endpoints; use dependency injection (`Depends`).

## 2. General Context of Key Functions

- **Plant Identification (`app/api/v1/endpoints/identification.py` & Services)**: 
  Handles multipart image uploads. Calls `plant.id` -> `GBIF` taxonomy -> `pgvector` RAG -> `OpenAI` to determine species. Uses confidence thresholds to determine if more user input is needed. Triggers background tasks to store images in Firebase.
- **Chatbot / LLM Pipeline (`app/api/v1/endpoints/chat.py` & `chat_service.py`)**: 
  Injects plant personality and sensor context into the system prompt. Uses Redis for active short-term context and Firestore for permanent logging. Uses a summarizer service when the context window gets too large.
- **Health Scoring (`health_service.py`)**:
  Calculates a weighted health score based on real-time sensor data and species care profiles. Updates Supabase records with `healthy`, `warning`, or `critical`.
- **Image Storage (`image_storage_service.py`)**:
  Compresses images using Pillow and coordinates deterministic path generation and Firebase uploads synchronously or as background tasks.
- **Security (`core/security.py`)**:
  Validates Supabase-issued JWTs. Every protected route depends on this.

## 3. Preparation for Migrations, Refactoring, and New Features

When refactoring or adding functionalities, strictly adhere to these rules:

1. **Keep Endpoints Thin**: Move all domain logic, API calls, and DB querying to `app/services/`. The API layer should only handle validation (via schemas) and HTTP responses.
2. **Dependency Injection**: Use FastAPI `Depends()` for DB and Auth. This simplifies unit testing.
3. **Database Schema is King**: Never assume database column names. Always check `migrations/schema.sql`. For instance, `plants.photo_url` is a computed field, while `plants.photo_storage_path` is the real column.
4. **Async Everything**: Use `async`/`await` for all DB interactions, API calls, and HTTP responses. 
5. **OpenAI Structured Outputs**: If modifying AI outputs, continue using the `response_format` pattern and test against live APIs, not just mocks.
6. **Graceful Degradation**: Continue to support fallback modes if Firebase credentials or MQTT configurations are missing, as established in the current code.
