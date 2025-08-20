# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KM24 Vejviser is a specialized AI-powered assistant that helps Danish journalists create structured investigation plans for the KM24 surveillance platform. The system takes natural language journalistic goals and generates strategic, pedagogical JSON plans that teach users advanced KM24 techniques.

## Core Architecture

### Backend Components
- **`main.py`**: FastAPI application with rate limiting, structured logging, and error handling
- **`advisor.py`**: Business logic for completing AI-generated plans with supplementary fields (warnings, power tips, geo advice)
- **`core/settings.py`**: Pydantic-based configuration management with `.env` support
- **`km24_knowledge_base_clean.yaml`**: Comprehensive YAML knowledge base containing KM24 modules, search syntax, and strategic principles

### Key Features
- **AI Integration**: Uses Anthropic Claude 3.5 Sonnet with sophisticated system prompts
- **JSON Output**: Structured response format with pedagogical fields (rationale, strategic_note, explanation)
- **Plan Completion**: Backend validates and enriches AI responses with missing required fields
- **Rate Limiting**: Implements request throttling using SlowAPI
- **Error Handling**: Comprehensive retry logic and graceful error responses

## Development Commands

### Setup
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API key in .env file
echo "ANTHROPIC_API_KEY=your_key_here" > .env
```

### Running the Application
```bash
# Start development server
uvicorn main:app --reload --port 8001

# Access at http://127.0.0.1:8001
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest test_main.py
pytest test_advisor.py
```

### Code Quality
Based on IMPROVEMENT_PLAN.md, the project plans to implement:
```bash
# Future linting and formatting (not yet implemented)
ruff check .
black .
mypy .
```

## Key Design Patterns

### Plan Completion System
The `complete_recipe()` function in `main.py:254-292` ensures all AI responses include required pedagogical fields:
- `strategic_note`: Module-specific warnings and advice
- `recommended_notification`: Notification cadence recommendations
- `power_tip`: Advanced user techniques based on module/search patterns
- `geo_advice`: Geographic guidance for location-based investigations
- `supplementary_modules`: Additional relevant modules with reasoning

### Configuration Management
Uses Pydantic BaseSettings in `core/settings.py` for type-safe environment variable handling. The application automatically loads `.env` files and provides sensible defaults.

### Error Handling
Implements a three-tier retry system for Anthropic API calls with exponential backoff. All errors are logged with structured information for debugging.

## API Endpoints

- `POST /generate-recipe/`: Main endpoint accepting `RecipeRequest` with journalistic goals
- `GET /health`: Health check with API configuration status
- `GET /`: Serves the web interface with inspiration prompts

## Testing Strategy

- **Unit Tests**: `test_advisor.py` covers business logic functions
- **Integration Tests**: `test_main.py` includes API endpoint testing and plan completion validation
- **API Key Handling**: Tests gracefully skip when Anthropic API key is not configured
- **Error Scenarios**: Comprehensive testing of edge cases and error conditions

## Knowledge Base

The `km24_knowledge_base_clean.yaml` contains:
- 45 official KM24 modules with metadata
- Advanced search syntax rules (`~phrase~`, `~word`, `;` operators)
- Strategic filtering principles
- Power-user techniques (Hitlogik, +1 trick)
- Common error patterns and solutions

This knowledge base drives the AI's understanding of KM24 capabilities and is referenced in the system prompt.