from pydantic import BaseModel, Field, model_validator


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country_codes: list[str] = Field(min_length=1)
    offer_id: int
    domain_id: int = 1813
    group_id: int = 10332
    traffic_source_id: int = 836

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_country_code(cls, value):
        if isinstance(value, dict) and "country_codes" not in value and "country_code" in value:
            return {**value, "country_codes": [value["country_code"]]}
        return value


class OfferMutation(BaseModel):
    offer_id: int


class OfferShareMutation(BaseModel):
    share: int = Field(ge=0, le=100)


class Catalogs(BaseModel):
    offers: list[dict]
    domains: list[dict]
    groups: list[dict]
    traffic_sources: list[dict]
