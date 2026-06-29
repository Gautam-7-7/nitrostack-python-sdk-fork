from nitrostack import injectable, tool, widget, ExecutionContext
from pydantic import BaseModel, Field
from typing import Literal, Optional
from modules.pizzaz.pizzaz_service import PizzazService

class ShowMapInput(BaseModel):
    filter: Literal["open_now", "top_rated", "all"] = Field(default="all", description="Filter to apply")

class ShowListInput(BaseModel):
    openNow: Optional[bool] = Field(default=None, description="Show only shops that are currently open")
    minRating: Optional[float] = Field(default=None, description="Minimum rating (1-5)")
    maxPrice: Optional[float] = Field(default=None, description="Maximum price level (1-3)")

class ShowShopInput(BaseModel):
    shopId: str = Field(description="ID of the pizza shop to display")

@injectable(deps=[PizzazService])
class PizzazTools:
    def __init__(self, service: PizzazService):
        self.service = service

    @tool(
        name="show_pizza_map",
        description="Display an interactive map of pizza shops in San Francisco",
        input_schema=ShowMapInput
    )
    @widget("pizza-map")
    async def show_pizza_map(self, input: ShowMapInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Showing pizza map with filter: {input.filter}")
        if input.filter == "open_now":
            shops = self.service.get_shops_filtered({"openNow": True})
        elif input.filter == "top_rated":
            shops = self.service.get_top_rated_shops()
        else:
            shops = self.service.get_all_shops()
            
        return {
            "shops": shops,
            "filter": input.filter,
            "totalShops": len(shops)
        }

    @tool(
        name="show_pizza_list",
        description="Display a list of pizza shops with details, ratings, and filters",
        input_schema=ShowListInput
    )
    @widget("pizza-list")
    async def show_pizza_list(self, input: ShowListInput, context: ExecutionContext) -> dict:
        context.logger.info("Showing pizza list")
        filters = {}
        if input.openNow is not None:
            filters["openNow"] = input.openNow
        if input.minRating is not None:
            filters["minRating"] = input.minRating
        if input.maxPrice is not None:
            filters["maxPrice"] = input.maxPrice
            
        shops = self.service.get_shops_filtered(filters)
        return {
            "shops": shops,
            "filters": {
                "openNow": input.openNow,
                "minRating": input.minRating,
                "maxPrice": input.maxPrice
            },
            "totalShops": len(shops)
        }

    @tool(
        name="show_pizza_shop",
        description="Display detailed page for a single pizza shop, including menu, ratings, hours, and photos",
        input_schema=ShowShopInput
    )
    @widget("pizza-shop")
    async def show_pizza_shop(self, input: ShowShopInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Showing pizza shop: {input.shopId}")
        shop = self.service.get_shop_by_id(input.shopId)
        if not shop:
            raise ValueError(f"Pizza shop not found: {input.shopId}")
        return {
            "shop": shop
        }
