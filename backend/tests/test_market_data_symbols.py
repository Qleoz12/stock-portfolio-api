import pytest

from services.market_data.ticker_symbols import yahoo_to_stooq_symbol


@pytest.mark.parametrize(
    "yahoo, stooq",
    [
        ("MSFT", "msft.us"),
        ("msft", "msft.us"),
        ("SHOP.TO", "shop.to"),
        ("VOD.L", "vod.uk"),
        ("BHP.AX", "bhp.ax"),
        ("AIR.PA", "air.pa"),
        ("BRK-B", "brk-b.us"),
    ],
)
def test_yahoo_to_stooq_symbol(yahoo: str, stooq: str):
    assert yahoo_to_stooq_symbol(yahoo) == stooq
