import pytest
from app.ingestion.models import RawDocument
from app.ingestion.pipeline import DocumentQualityPipeline

@pytest.fixture
def pipeline():
    return DocumentQualityPipeline()

def test_canonicalize_url(pipeline):
    # Test index.php stripping
    assert pipeline._canonicalize_url("https://example.com/index.php") == "https://example.com/"
    assert pipeline._canonicalize_url("https://example.com/sub/index.php") == "https://example.com/sub"
    
    # Test index.html stripping
    assert pipeline._canonicalize_url("https://example.com/index.html") == "https://example.com/"
    
    # Test trailing slash
    assert pipeline._canonicalize_url("https://example.com/about/") == "https://example.com/about"
    assert pipeline._canonicalize_url("https://example.com/") == "https://example.com/"
    
    # Test complex urls
    assert pipeline._canonicalize_url("https://example.com/index.php/about.php") == "https://example.com/index.php/about.php" # Only strips if it's the end of path

def test_clean_markdown(pipeline):
    raw_md = "Hello\n\n\n\nWorld! [](https://empty.link) [Valid](link)"
    clean = pipeline._clean_markdown(raw_md)
    assert clean == "Hello\n\nWorld!  [Valid](link)"

def test_quality_score(pipeline):
    # Duplicate
    assert pipeline._calculate_quality_score("Long enough text here...", "Title", True) == 0
    
    # Short
    assert pipeline._calculate_quality_score("Short", "Title", False) < 100
    
    # No title
    assert pipeline._calculate_quality_score("A somewhat long text that exceeds the 200 character minimum easily if we just keep typing random words here until it gets there. We are testing the fact that having no title will drop the score. Just a bit more text to be safe.", "", False) == 90

@pytest.mark.asyncio
async def test_pipeline_process(pipeline):
    # Setup raw stream
    async def mock_stream():
        yield RawDocument("https://example.com/index.php", "Content A", {"title": "A"})
        yield RawDocument("https://example.com/about", "Content A", {"title": "About"}) # Duplicate content
        yield RawDocument("https://example.com/contact", "Content B which is very short", {"title": "Contact"})

    results = []
    async for doc in pipeline.process(mock_stream()):
        results.append(doc)

    assert len(results) == 3
    
    # Check A
    assert results[0].canonical_url == "https://example.com/"
    assert results[0].is_duplicate == False
    
    # Check duplicate
    assert results[1].canonical_url == "https://example.com/about"
    assert results[1].is_duplicate == True
    assert results[1].quality_score == 0
    
    # Check short
    assert results[2].is_duplicate == False
    assert results[2].quality_score < 100
    
    report = pipeline.get_report()
    assert report["total_processed"] == 3
    assert report["duplicates_removed"] == 1
