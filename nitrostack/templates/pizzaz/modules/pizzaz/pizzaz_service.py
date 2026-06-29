from nitrostack import injectable
from modules.pizzaz.pizzaz_data import PIZZA_SHOPS

@injectable()
class PizzazService:
    def get_all_shops(self):
        return PIZZA_SHOPS

    def get_shop_by_id(self, shop_id: str):
        for shop in PIZZA_SHOPS:
            if shop["id"] == shop_id:
                return shop
        return None

    def get_shops_filtered(self, filters: dict):
        shops = PIZZA_SHOPS
        if filters.get("openNow"):
            shops = [shop for shop in shops if shop["openNow"]]
        if filters.get("minRating") is not None:
            shops = [shop for shop in shops if shop["rating"] >= filters["minRating"]]
        if filters.get("maxPrice") is not None:
            shops = [shop for shop in shops if shop["priceLevel"] <= filters["maxPrice"]]
        if filters.get("cuisine"):
            cuisine_lower = filters["cuisine"].lower()
            shops = [
                shop for shop in shops
                if any(cuisine_lower in c.lower() for c in shop["cuisine"])
            ]
        return shops

    def get_top_rated_shops(self, limit: int = 5):
        sorted_shops = sorted(PIZZA_SHOPS, key=lambda x: x["rating"], reverse=True)
        return sorted_shops[:limit]
