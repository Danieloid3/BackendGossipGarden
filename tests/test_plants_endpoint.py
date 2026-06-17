"""Tests del endpoint REST de plants (personalized care)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock
import pytest

@pytest.mark.asyncio
async def test_generate_personalized_care_success(client):
    plant_mock_data = {
        "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "location": "Sala",
        "estimated_age_months": 24,
        "species": {"scientific_name": "Monstera deliciosa", "common_name": "Ceriman"}
    }
    
    mock_tips = {"watering": "test"}
    
    with patch("app.api.v1.endpoints.plants.supabase") as sb, \
         patch("app.services.openai_service.generate_personalized_care", new_callable=AsyncMock) as mock_gen, \
         patch("app.api.v1.endpoints.plants._flatten_species") as mock_flatten, \
         patch("app.api.v1.endpoints.plants._photo_url") as mock_photo:
         
        # Mock fetch plant
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[plant_mock_data])
        
        # Mock generate_personalized_care
        mock_gen.return_value = mock_tips
        
        # Mock update
        sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": 1}])
        
        # Mock refetch
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[plant_mock_data])
        mock_photo.return_value = "http://test.url"
        
        res = await client.post(
            "/api/v1/plants/8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab/personalized-care", 
            json={"city": "Medellin", "language": "fr"}
        )

    assert res.status_code == 200
    mock_gen.assert_called_once_with(
        species_name="Monstera deliciosa",
        location="Sala",
        city="Medellin",
        language="fr",
        estimated_age_months=24
    )

@pytest.mark.asyncio
async def test_generate_personalized_care_no_location(client):
    plant_mock_data = {
        "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "location": None, # Missing location
        "species": {"scientific_name": "Monstera deliciosa"}
    }
    
    with patch("app.api.v1.endpoints.plants.supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[plant_mock_data])
        res = await client.post(
            "/api/v1/plants/8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab/personalized-care", 
            json={"city": "Bogota"}
        )
    assert res.status_code == 400
    assert "ubicación" in res.json()["detail"]

@pytest.mark.asyncio
async def test_generate_personalized_care_not_found(client):
    with patch("app.api.v1.endpoints.plants.supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        res = await client.post(
            "/api/v1/plants/8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab/personalized-care", 
            json={"city": "Bogota"}
        )
    assert res.status_code == 404
