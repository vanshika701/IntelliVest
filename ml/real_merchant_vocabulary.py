"""Supplementary training data: real merchant/brand vocabulary.

Why this exists: mitulshah/transaction-categorization's merchant names
are template placeholders (e.g. "Exxon - CANADA Store") — real brands
like Swiggy, Zerodha, or BESCOM never appear in it. A stress test against
realistic text (see evaluate_on_realistic_examples.py) measured only 50%
accuracy for exactly this reason: the model has zero learned signal for
real merchant names. This module fixes the input, not the model — real
brand names, mapped to the same 10 categories, with several realistic
statement-formatting variations per brand (since real statements vary a
lot in format even for the same merchant).

Deliberately uses DIFFERENT exact strings than
evaluate_on_realistic_examples.py's 50 stress-test examples — the goal is
for the model to learn that the *brand token* ("swiggy") predicts a
category regardless of surrounding format, and then get tested on a
different format it hasn't seen. If training and test strings were near-
identical, an accuracy improvement would just be memorization, not
generalization, and wouldn't tell us anything honest.
"""

# category -> list of (brand, [format templates using {brand}])
_CATEGORY_BRANDS: dict[str, list[str]] = {
    "Food & Dining": [
        "Swiggy", "Zomato", "McDonalds", "KFC", "Dominos", "Pizza Hut",
        "Subway", "Burger King", "Dunkin Donuts", "Cafe Coffee Day",
        "Barbeque Nation", "Haldirams", "Behrouz Biryani", "Faasos",
        "Chaayos", "Third Wave Coffee", "Wow Momo", "Box8",
    ],
    "Transportation": [
        "Uber", "Ola", "Rapido", "IRCTC", "Indian Oil", "Bharat Petroleum",
        "Hindustan Petroleum", "Delhi Metro", "Namma Metro", "RedBus",
        "MakeMyTrip Flight", "IndiGo Airlines", "Yulu Bike",
    ],
    "Shopping & Retail": [
        "Amazon", "Flipkart", "Myntra", "Ajio", "Nykaa", "Reliance Trends",
        "DMart", "Big Bazaar", "Croma", "Decathlon", "IKEA", "Lenskart",
        "FirstCry", "Meesho", "Tata Cliq",
    ],
    "Entertainment & Recreation": [
        "Netflix", "Spotify", "Hotstar", "Amazon Prime Video",
        "BookMyShow", "PVR Cinemas", "INOX", "YouTube Premium", "SonyLIV",
        "Zee5", "PlayStation Store", "Steam", "Apple Music",
    ],
    "Healthcare & Medical": [
        "Apollo Pharmacy", "Practo", "1mg", "PharmEasy", "Fortis Hospital",
        "Max Healthcare", "Manipal Hospital", "Medplus", "Cult.fit",
        "Netmeds", "Cloudnine Hospital",
    ],
    "Utilities & Services": [
        "BESCOM", "Airtel", "Jio", "Vodafone Idea", "ACT Fibernet",
        "Mahanagar Gas", "Tata Power", "BSES Rajdhani", "Adani Electricity",
        "Hathway Broadband", "BWSSB Water",
    ],
    "Financial Services": [
        "Zerodha", "Groww", "CRED", "Paytm", "PhonePe", "LIC",
        "HDFC Mutual Fund", "ICICI Direct", "Upstox", "Policybazaar",
        "Angel One", "Google Pay",
    ],
    "Income": [
        "TCS Salary", "Infosys Salary", "Wipro Salary", "Accenture Salary",
        "HCL Salary", "Freelance Payment", "Consulting Fee Credit",
        "Bonus Payout", "Reimbursement Credit",
    ],
    "Government & Legal": [
        "Income Tax Department", "GST Payment", "Municipal Corporation",
        "RTO", "Passport Seva", "EPFO", "Court Fee", "E-Challan",
        "Aadhaar Enrollment", "Stamp Duty",
    ],
    "Charity & Donations": [
        "GiveIndia", "PM Cares Fund", "Akshaya Patra", "CRY India",
        "Smile Foundation", "Indian Red Cross", "Goonj", "HelpAge India",
        "Save the Children India",
    ],
}

# Realistic statement-formatting templates, applied per brand. Not every
# template makes sense for every brand, but variety across the whole set
# is what matters — real statements are inconsistent like this.
_FORMAT_TEMPLATES = [
    "{brand} PAYMENT",
    "POS DEBIT {brand_upper}",
    "UPI-{brand_upper}-{ref}",
    "{brand_upper}*{ref}",
    "NEFT-{brand_upper}",
    "{brand} ONLINE ORDER",
    "{brand_upper} PVT LTD",
    "AUTOPAY {brand_upper}",
]

_REF_CODES = ["4521", "9C3F1A", "BLR2601", "778821", "IN0092"]

# Targeted fixes for specific token-collision errors found by the
# realistic-text stress test (see ml/log.md) — a model trained on the
# rows above still confidently mispredicted these:
#   - "LIC PREMIUM AUTO DEBIT" -> Transportation. "auto" alone is
#     dominated by vehicle-related rows in the main dataset; these rows
#     teach "auto debit"/"auto pay" as a phrase meaning automatic
#     payment, not a vehicle, across several Financial Services brands.
#   - "GAMEZOP ENT PVT LTD" -> Healthcare & Medical. "ENT" collides with
#     the medical abbreviation (ear-nose-throat) in the main dataset;
#     these rows give "ENT" a positive Entertainment & Recreation signal
#     too, since Indian company names commonly abbreviate "Entertainment"
#     this way.
#   - "AMZN Mktp IN*..." -> Food & Dining. The abbreviated "AMZN Mktp"
#     form (distinct from the spelled-out "Amazon" rows above) wasn't
#     represented at all.
# Deliberately different exact strings than both the general templates
# above and evaluate_on_realistic_examples.py's stress-test strings, for
# the same generalization-not-memorization reason described in the
# module docstring.
_DISAMBIGUATION_EXAMPLES: list[tuple[str, str]] = [
    ("LIC AUTO DEBIT PREMIUM PYMT", "Financial Services"),
    ("HDFC MF AUTO PAY SIP", "Financial Services"),
    ("ICICI CARD AUTODEBIT EMI", "Financial Services"),
    ("ZERODHA AUTO INVEST DEBIT", "Financial Services"),
    ("POLICYBAZAAR PREMIUM AUTO DEBIT", "Financial Services"),
    ("GROWW SIP AUTO PAYMENT DEBIT", "Financial Services"),
    ("BOOKMYSHOW ENT PVT LTD", "Entertainment & Recreation"),
    ("PVR ENT PRODUCTIONS LTD", "Entertainment & Recreation"),
    ("INOX ENT LEISURE PVT LTD", "Entertainment & Recreation"),
    ("SONY ENT NETWORK SUB", "Entertainment & Recreation"),
    ("ZEE ENT ENTERPRISES LTD", "Entertainment & Recreation"),
    ("AMZN MKTP IN AMAZON PURCHASE", "Shopping & Retail"),
    ("AMZN MKTP US ORDER PYMT", "Shopping & Retail"),
    ("AMAZON MKTP IN*RETAIL BILL", "Shopping & Retail"),
]


def generate_supplementary_dataset() -> list[tuple[str, str]]:
    """Returns [(transaction_description, category), ...] — real brand
    names in realistic formats, several variations per brand, plus a
    small set of targeted disambiguation rows for specific known
    token-collision errors (see _DISAMBIGUATION_EXAMPLES)."""
    rows = []
    for category, brands in _CATEGORY_BRANDS.items():
        for i, brand in enumerate(brands):
            # Not every brand gets every template — that would make the
            # set larger than needed and overly repetitive in structure.
            # Rotating through templates per brand still covers the full
            # template set across the category while keeping variety.
            for j in range(4):
                template = _FORMAT_TEMPLATES[(i + j) % len(_FORMAT_TEMPLATES)]
                ref = _REF_CODES[(i + j) % len(_REF_CODES)]
                description = template.format(brand=brand, brand_upper=brand.upper(), ref=ref)
                rows.append((description, category))
    rows.extend(_DISAMBIGUATION_EXAMPLES)
    return rows


if __name__ == "__main__":
    # Quick sanity check when run directly: print a few examples per
    # category and the total count.
    data = generate_supplementary_dataset()
    print(f"Generated {len(data)} supplementary rows across {len(_CATEGORY_BRANDS)} categories.\n")
    seen_categories = set()
    for description, category in data:
        if category not in seen_categories:
            seen_categories.add(category)
            print(f"{category}: {description!r}")
