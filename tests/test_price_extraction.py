"""Price-extraction regression tests for the Computech listing parser.

Found 2026-08-17 by adding price sorting to the catalog: the cheapest CPUs were all
priced at 1851, which is not a price but the LGA1851 socket in their titles. The card
regex made the rupee sign optional and took the first 4-6 digit number in the card,
and a card's text begins with the product title. 57% of that store's 1,906 products
carried a price identical to a number in their own name.

Verified live against computechstore.in the same day: "Colorful iGame GeForce RTX 5080
Ultra OC 16GB" parsed as Rs 5,080 against a real listed price of Rs 1,54,499.

These tests run offline against synthetic cards shaped like the real markup.
"""
import pytest

from domain.store import Store
from scrapers.generic_parser import GenericParser


@pytest.fixture
def parser():
    return GenericParser(
        Store(
            id=8,
            name="computechstore",
            display_name="Computech Store",
            domain="computechstore.in",
            base_url="https://computechstore.in",
            currency="INR",
            currency_symbol="₹",
            search_config={},
            product_config={},
            active=True,
        )
    )


def _card(title: str, price: str, mrp: str | None = None) -> str:
    """A listing card shaped like the real one.

    Matches what computechstore.in actually serves, checked live on 2026-08-17:
    the title comes first, amounts carry no thousands separators, the current price
    precedes the struck-through MRP, and there is no `.price` element in the card -
    which is why this parser reads the card text rather than a selector.
    """
    mrp_html = f"<del>₹{mrp}</del>" if mrp else ""
    return f"""
    <div class="product">
      <div>
        <a href="https://computechstore.in/product/{title.lower().replace(' ', '-')}/">{title}</a>
        <span><ins>₹{price}</ins>{mrp_html}</span>
        <span>In Stock</span>
      </div>
    </div>
    """


@pytest.mark.parametrize(
    "title, listed_price, decoy",
    [
        # Every decoy below is a real number that used to win over the actual price.
        # The first four were measured against the live site on 2026-08-17.
        ("Colorful iGame GeForce RTX 5080 Ultra OC 16GB", "154499", "5080"),
        ("NEXTRON RX 7600 XT 16GB Graphics Card", "34999", "7600"),
        ("ASRock RX 9050 Challenger 8GB GDDR6", "30999", "9050"),
        ("Colorful iGame GeForce RTX 5070 Ti Ultra OC SFF 16GB", "124499", "5070"),
        ("Intel Core Ultra 5 245K LGA1851 Desktop Processor", "32500", "1851"),
        ("ADATA XPG ARMAX 16GB 5600MHz CL46 DDR5 RAM", "4899", "5600"),
        ("Corsair RM1000e 1000W Gold Modular Power Supply", "12750", "1000"),
    ],
)
def test_model_numbers_in_the_title_are_not_read_as_the_price(
    parser, title, listed_price, decoy
):
    results = parser._parse_computech_html(_card(title, listed_price))

    assert len(results) == 1, f"card for {title!r} did not parse"
    price = results[0].price
    assert str(int(price)) != decoy, (
        f"{title!r} priced at {price} - that is the {decoy} from its own title, not a price"
    )
    assert int(price) == int(listed_price)


def test_mrp_is_still_read_when_present(parser):
    """Live card order is current price first, struck-through MRP second."""
    results = parser._parse_computech_html(
        _card("NEXTRON RX 7600 XT 16GB Graphics Card", "34999", mrp="74800")
    )
    assert results[0].price == 34999
    assert results[0].mrp == 74800


def test_card_without_a_marked_price_is_skipped_not_invented(parser):
    """A title full of numbers and no rupee-marked amount must yield nothing at all.

    Dropping the listing is correct; the previous behaviour was to sell an RTX 5080
    for 5080.
    """
    card = """
    <div class="product">
      <div>
        <a href="https://computechstore.in/product/rtx-5080/">Colorful RTX 5080 16GB 1000W</a>
        <span>In Stock</span>
      </div>
    </div>
    """
    assert parser._parse_computech_html(card) == []


def test_out_of_stock_cards_are_skipped(parser):
    card = _card("NEXTRON RX 7600 XT", "34999").replace("In Stock", "Out of Stock")
    assert parser._parse_computech_html(card) == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("₹31,999", 31999),
        ("₹31,999.00", 31999),
        ("31999", 31999),
        # TLG Gaming (OpenCart Journal 3). The old cleaner only stripped "₹" and
        # commas, so each of these raised and answered 0 - which is why all 163 of
        # that store's products were priced zero and vanished from the catalog.
        ("Rs.31,999.00", 31999),
        ("Rs. 31,999", 31999),
        ("INR 31999", 31999),
        # The .price container concatenates the selling price and the tax line; the
        # first amount is the one shown to the shopper.
        ("Rs.31,999.00Ex Tax:Rs.27,117.80", 31999),
        ("", 0),
        ("Call for price", 0),
    ],
)
def test_clean_price_reads_first_amount_whatever_the_currency_prefix(
    parser, text, expected
):
    assert int(parser._clean_price(text)) == expected


# --- Title completeness ------------------------------------------------------
# PCStudio's theme clamps long names, rendering the visible text elided while the
# whole name sits in a nested `title` attribute. Reading the visible text stored a
# truncated name for 1,793 products (15% of the catalog). It broke search, corrupted
# canonical keys built from the name, and fed incomplete text to spec extraction - a
# DDR5-6000 CL30 kit was extracted as "CL3" because that is where the title stopped.

from bs4 import BeautifulSoup  # noqa: E402


def _title_el(html: str):
    return BeautifulSoup(html, "lxml").select_one("a")


def test_full_title_prefers_the_attribute_when_text_is_elided(parser):
    el = _title_el(
        '<a><span title="TEAMGROUP T-FORCE DELTA RGB DDR5 6,000 MHz 32 GB 16 GB x 2 Ram">'
        'TEAMGROUP T-FORCE DELTA RGB DDR5 6,000 M...</span></a>'
    )
    assert parser._full_title(el) == (
        "TEAMGROUP T-FORCE DELTA RGB DDR5 6,000 MHz 32 GB 16 GB x 2 Ram"
    )


def test_full_title_leaves_untruncated_text_alone(parser):
    el = _title_el('<a><span title="Some Unrelated Tooltip">Corsair Vengeance 32GB</span></a>')
    assert parser._full_title(el) == "Corsair Vengeance 32GB"


def test_full_title_ignores_an_attribute_that_disagrees_with_the_visible_text(parser):
    """A theme using `title` for something else must not overwrite the name."""
    el = _title_el(
        '<a><span title="Add this item to your shopping cart right now">'
        'Corsair Vengeance 32GB DDR5 6000MHz...</span></a>'
    )
    assert parser._full_title(el) == "Corsair Vengeance 32GB DDR5 6000MHz..."


def test_full_title_handles_unicode_ellipsis(parser):
    el = _title_el('<a><span title="Asus Prime H510M-E LGA1200 mATX Motherboard">'
                   'Asus Prime H510M-E LGA1200 mATX…</span></a>')
    assert parser._full_title(el) == "Asus Prime H510M-E LGA1200 mATX Motherboard"
