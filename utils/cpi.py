"""
Historical Consumer Price Index (CPI) Inflation Calculator.
Combines historical price series (Minneapolis Fed / US BLS CPI-U estimates from 1800 to present).
Provides deterministic, inflation-adjusted price conversions for the 'price' format.
"""

from typing import Tuple

# Historical CPI index values (base year ~1982-84 = 100 or linked series)
# Source: Federal Reserve Bank of Minneapolis / U.S. Bureau of Labor Statistics
CPI_HISTORICAL_INDEX = {
    1800: 17.0, 1805: 19.0, 1810: 17.0, 1815: 18.0, 1820: 13.0,
    1825: 11.0, 1830: 10.0, 1835: 10.0, 1840: 10.0, 1845: 8.5,
    1850: 8.3, 1855: 9.0, 1860: 9.0, 1861: 9.5, 1862: 11.0,
    1863: 13.0, 1864: 16.0, 1865: 17.0, 1870: 14.0, 1875: 12.0,
    1880: 10.0, 1881: 10.0, 1882: 10.0, 1883: 9.8, 1884: 9.6,
    1885: 9.3, 1886: 9.0, 1887: 9.1, 1888: 9.1, 1889: 9.0,
    1890: 9.1, 1891: 9.1, 1892: 9.1, 1893: 9.0, 1894: 8.7,
    1895: 8.5, 1896: 8.5, 1897: 8.5, 1898: 8.5, 1899: 8.5,
    1900: 8.6, 1901: 8.7, 1902: 8.9, 1903: 9.2, 1904: 9.3,
    1905: 9.2, 1906: 9.4, 1907: 9.8, 1908: 9.5, 1909: 9.4,
    1910: 9.8, 1911: 9.8, 1912: 10.1, 1913: 9.9, 1914: 10.0,
    1915: 10.1, 1916: 10.9, 1917: 12.8, 1918: 15.0, 1919: 17.3,
    1920: 20.0, 1921: 17.9, 1922: 16.8, 1923: 17.1, 1924: 17.1,
    1925: 17.5, 1926: 17.7, 1927: 17.4, 1928: 17.1, 1929: 17.1,
    1930: 16.7, 1935: 13.7, 1940: 14.0, 1945: 18.0, 1950: 24.1,
    1960: 29.6, 1970: 38.8, 1980: 82.4, 1990: 130.7, 2000: 172.2,
    2010: 218.1, 2020: 258.8, 2024: 314.2, 2025: 322.0, 2026: 330.0
}

CURRENT_YEAR = 2026
CURRENT_CPI = CPI_HISTORICAL_INDEX[CURRENT_YEAR]

def get_cpi_for_year(year: int) -> float:
    """Returns the CPI index for a given year, interpolating if missing."""
    if year in CPI_HISTORICAL_INDEX:
        return CPI_HISTORICAL_INDEX[year]
    
    known_years = sorted(CPI_HISTORICAL_INDEX.keys())
    if year <= known_years[0]:
        return CPI_HISTORICAL_INDEX[known_years[0]]
    if year >= known_years[-1]:
        return CPI_HISTORICAL_INDEX[known_years[-1]]
    
    # Linear interpolation
    lower_year = max(y for y in known_years if y < year)
    upper_year = min(y for y in known_years if y > year)
    lower_cpi = CPI_HISTORICAL_INDEX[lower_year]
    upper_cpi = CPI_HISTORICAL_INDEX[upper_year]
    
    slope = (upper_cpi - lower_cpi) / (upper_year - lower_year)
    return lower_cpi + slope * (year - lower_year)

def calculate_inflation(past_amount_dollars: float, past_year: int) -> Tuple[float, float]:
    """
    Calculates the equivalent modern dollar amount and multiplier.
    Returns: (today_amount_dollars, multiplier)
    """
    past_cpi = get_cpi_for_year(past_year)
    multiplier = CURRENT_CPI / past_cpi
    today_amount = past_amount_dollars * multiplier
    return round(today_amount, 2), round(multiplier, 1)

def format_price_comparison(past_cents: int, past_year: int, item_name: str) -> str:
    """
    Formats clean comparison strings for card overlay and post text:
    Example: '1903: 15¢ (approx. $5.38 today) — a 35.9x increase'
    """
    past_dollars = past_cents / 100.0
    today_dollars, mult = calculate_inflation(past_dollars, past_year)
    
    if past_cents < 100:
        past_str = f"{past_cents}¢"
    else:
        past_str = f"${past_dollars:.2f}"
        
    return (
        f"In {past_year}, {item_name} cost {past_str}. "
        f"In today's dollars, that is roughly ${today_dollars:,.2f}."
    )
