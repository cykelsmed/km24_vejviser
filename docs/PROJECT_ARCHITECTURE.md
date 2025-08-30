# KM24 Vejviser - Technical Architecture

## Overview

KM24 Vejviser is a FastAPI-based application that generates structured investigation plans for journalists using KM24 monitoring platform. The system combines LLM (Claude 3.5 Sonnet) with dynamic filter recommendations and robust validation.

## Architecture Components

### 1. Core Application (`main.py`)

**Purpose**: Main FastAPI application with LLM integration and recipe generation.

**Key Components**:
- FastAPI app with rate limiting
- LLM client (Anthropic Claude 3.5 Sonnet)
- Recipe generation pipeline
- Validation and post-processing
- API endpoints

**Main Functions**:
- `get_anthropic_response()`: Generates raw LLM output
- `complete_recipe()`: Post-processes and validates recipes
- `coerce_raw_to_target_shape()`: Normalizes LLM output
- `_ensure_filters_before_search_string()`: Injects dynamic filters

### 2. KM24 API Client (`km24_client.py`)

**Purpose**: Handles all interactions with the external KM24 API.

**Features**:
- Caching with TTL (Time To Live)
- Rate limiting
- Error handling and retries
- Health status monitoring

**Key Methods**:
- `get_modules_basic()`: Fetch basic module information
- `get_modules_detailed()`: Fetch detailed module data
- `get_filter_options()`: Get available filter options
- `get_municipalities()`: Fetch municipality data
- `get_branch_codes_detailed()`: Fetch industry codes

### 3. Filter Catalog (`filter_catalog.py`)

**Purpose**: Dynamic filter recommendation system with semantic relevance scoring.

**Core Classes**:
- `FilterCatalog`: Main filter management class
- `FilterRecommendation`: Data structure for filter recommendations
- `Municipality`: Municipality data structure
- `BranchCode`: Industry code data structure

**Key Features**:
- Semantic relevance scoring based on goal keywords
- Caching of filter data
- Fallback to test data when API is unavailable
- Module-specific filter recommendations

**Relevance Algorithm**:
```python
def _calculate_semantic_relevance(self, text: str, keywords: list[str]) -> float:
    """Calculate semantic relevance score between text and keywords."""
    text_lower = text.lower()
    score = 0.0
    
    for keyword in keywords:
        if keyword.lower() in text_lower:
            score += 1.0
        # Partial matches
        elif any(word in text_lower for word in keyword.split()):
            score += 0.5
    
    return score / len(keywords) if keywords else 0.0
```

### 4. Module Validator (`module_validator.py`)

**Purpose**: Validates and enriches module information.

**Features**:
- Module validation against KM24 specifications
- Web source detection
- API example generation
- Module metadata enrichment

### 5. Data Models (`models/`)

**Purpose**: Pydantic models for request/response validation.

**Key Models**:
- `RecipeRequest`: Input validation for recipe generation
- `UseCaseResponse`: Output validation for generated recipes
- Various validation models for different data structures

## Data Flow

### Recipe Generation Pipeline

1. **Input Validation**: `RecipeRequest` validates user input
2. **LLM Generation**: `get_anthropic_response()` generates raw JSON
3. **Filter Injection**: `_ensure_filters_before_search_string()` adds dynamic filters
4. **Normalization**: `coerce_raw_to_target_shape()` structures the output
5. **Module Validation**: `module_validator.py` enriches module data
6. **Final Validation**: `validate_km24_recipe()` ensures KM24 compliance
7. **Response**: Structured JSON returned to client

### Filter Recommendation Flow

1. **Goal Analysis**: Parse user goal for keywords
2. **Semantic Matching**: Score relevance against filter data
3. **Filter Selection**: Select top-scoring filters
4. **Context Enhancement**: Add regional and industry context
5. **Injection**: Inject filters into recipe steps

## Caching Strategy

### KM24 API Cache
- **Location**: `cache/` directory
- **TTL**: 24 hours for most data
- **Format**: JSON files with timestamps
- **Invalidation**: Manual via `/api/clear-cache` endpoint

### Filter Catalog Cache
- **Location**: In-memory with `FilterCatalog` class
- **TTL**: 1 hour for dynamic data
- **Fallback**: Test data when API unavailable

## Error Handling

### LLM Errors
- API key validation
- Rate limit handling
- Malformed response recovery
- Fallback to default templates

### KM24 API Errors
- Connection timeout handling
- Retry logic with exponential backoff
- Fallback to cached data
- Graceful degradation to test data

### Validation Errors
- Structured error messages
- Specific field validation
- KM24 rule compliance checking
- User-friendly error formatting

## Security Considerations

### API Key Management
- Environment variable storage
- Runtime validation
- Secure error messages (no key exposure)

### Rate Limiting
- Per-endpoint limits
- User-based throttling
- Configurable limits via `limiter.limit()`

### Input Sanitization
- Pydantic validation
- SQL injection prevention
- XSS protection in templates

## Performance Optimization

### Caching
- Multi-level caching strategy
- Intelligent cache invalidation
- Memory and disk caching

### Async Operations
- Non-blocking API calls
- Concurrent filter loading
- Background cache updates

### Database Optimization
- Efficient JSON storage
- Indexed cache lookups
- Minimal API calls

## Testing Strategy

### Test Organization
- **Location**: `tests/` directory
- **Structure**: Separate files for different components
- **Coverage**: Unit, integration, and API tests

### Test Categories
- **Unit Tests**: Individual function testing
- **Integration Tests**: Component interaction testing
- **API Tests**: Endpoint functionality testing
- **Validation Tests**: KM24 rule compliance testing

### Test Data
- Mock KM24 API responses
- Synthetic filter data
- Test user scenarios

## Deployment Considerations

### Environment Variables
```bash
ANTHROPIC_API_KEY=your_api_key_here
KM24_API_BASE_URL=https://api.km24.dk
CACHE_TTL=86400
RATE_LIMIT=5/minute
```

### Dependencies
- Python 3.8+
- FastAPI
- Anthropic SDK
- Pydantic
- Pytest (development)

### Production Setup
- Gunicorn for WSGI server
- Nginx for reverse proxy
- Redis for session storage (optional)
- Monitoring and logging

## Monitoring and Logging

### Logging Strategy
- Structured logging with levels
- Request/response logging
- Error tracking with context
- Performance metrics

### Health Checks
- `/health` endpoint
- KM24 API status monitoring
- LLM connectivity testing
- Cache status reporting

## Future Enhancements

### Planned Features
- Advanced semantic search
- Machine learning relevance scoring
- Real-time filter updates
- Multi-language support
- Advanced analytics dashboard

### Technical Improvements
- GraphQL API
- WebSocket support for real-time updates
- Microservice architecture
- Container deployment
- CI/CD pipeline

## Troubleshooting Guide

### Common Issues

**LLM Not Responding**
- Check API key configuration
- Verify rate limits
- Check network connectivity

**Filter Recommendations Not Working**
- Verify KM24 API connectivity
- Check cache status
- Review filter catalog configuration

**Validation Errors**
- Check KM24 rule compliance
- Verify JSON structure
- Review module specifications

### Debug Endpoints
- `/api/filter-catalog/status`: Filter system status
- `/api/km24-status`: KM24 API connectivity
- `/health`: Overall system health

## Contributing

### Development Setup
1. Clone repository
2. Install dependencies
3. Set up environment variables
4. Run tests
5. Start development server

### Code Standards
- PEP 8 compliance
- Type hints required
- Docstrings for all functions
- Comprehensive test coverage

### Pull Request Process
1. Create feature branch
2. Add tests for new functionality
3. Update documentation
4. Submit pull request
5. Code review and approval
