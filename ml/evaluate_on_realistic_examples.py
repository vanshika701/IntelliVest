"""Realistic-text stress test for the expense categorizer.

The training dataset (mitulshah/transaction-categorization) is
template-generated — clean, regular text like "Exxon - CANADA Store".
Real bank/UPI/NEFT statements look nothing like that. This module's
`evaluate()` measures the actual gap between the two, rather than just
asserting one exists in a comment.

`evaluate()` is imported and called automatically at the end of
ml/train_expense_categorizer.py, so every future training run documents
this gap fresh in metrics.json. Run this file directly to stress-test
whatever model is currently saved on disk:

    cd ml && python3 evaluate_on_realistic_examples.py
"""

# Hand-written, not from the training dataset. Styled after real Indian
# bank/UPI/NEFT statement text (actual brand names, abbreviations,
# reference numbers) rather than the training data's clean "Merchant -
# COUNTRY Suffix" template — this is the actual gap we want to measure.
REALISTIC_EXAMPLES = [
    ("POS DEBIT SWIGGY BANGALORE", "Food & Dining"),
    ("ZOMATO ORDER #4521", "Food & Dining"),
    ("MCD DRIVE THRU 00234", "Food & Dining"),
    ("STARBUCKS RESERVE MUMBAI", "Food & Dining"),
    ("DOMINOS PIZZA-HSR LAYOUT", "Food & Dining"),
    ("BEHROUZ BIRYANI ORDER", "Food & Dining"),
    ("CHAI POINT KIOSK PYMT", "Food & Dining"),
    ("FAASOS WRAP DELIVERY", "Food & Dining"),
    ("HALDIRAM SWEETS BILL", "Food & Dining"),
    ("SUBWAY SANDWICH ARTIST", "Food & Dining"),
    ("KFC BUCKET MEAL ORDER", "Food & Dining"),
    ("CCD COFFEE DAY OUTLET", "Food & Dining"),
    ("WOW MOMO STEAM BILL", "Food & Dining"),
    ("BARBEQUE NATION DINNER", "Food & Dining"),
    ("THIRD WAVE COFFEE ROASTERS", "Food & Dining"),
    ("UBER TRIP 8827FK", "Transportation"),
    ("OLA CABS-BLR-2601", "Transportation"),
    ("IRCTC RAIL TICKET BKG", "Transportation"),
    ("METRO CARD RECHARGE DELHI", "Transportation"),
    ("INDIAN OIL FUEL PUMP #4521", "Transportation"),
    ("RAPIDO BIKE TAXI FARE", "Transportation"),
    ("REDBUS TICKET BOOKING", "Transportation"),
    ("MAKEMYTRIP FLIGHT PNR", "Transportation"),
    ("INDIGO AIRLINES BAGGAGE", "Transportation"),
    ("YULU BIKE RENTAL FARE", "Transportation"),
    ("BHARAT PETROLEUM FUEL", "Transportation"),
    ("HP PETROL PUMP BILL", "Transportation"),
    ("NAMMA METRO SMART CARD", "Transportation"),
    ("OLA AUTO RIDE FARE", "Transportation"),
    ("PARKING FEE MG ROAD", "Transportation"),
    ("AMZN Mktp IN*2K3RT4RF4", "Shopping & Retail"),
    ("FLIPKART INTERNET PVT LTD", "Shopping & Retail"),
    ("RELIANCE TRENDS PUR", "Shopping & Retail"),
    ("DMART RETAIL BILL#7723", "Shopping & Retail"),
    ("MYNTRA DESIGNS PVT", "Shopping & Retail"),
    ("AJIO FASHION ORDER", "Shopping & Retail"),
    ("NYKAA BEAUTY PRODUCTS", "Shopping & Retail"),
    ("CROMA ELECTRONICS BILL", "Shopping & Retail"),
    ("DECATHLON SPORTS GEAR", "Shopping & Retail"),
    ("IKEA FURNITURE PUR", "Shopping & Retail"),
    ("LENSKART EYEWEAR ORDER", "Shopping & Retail"),
    ("BIG BAZAAR GROCERY BILL", "Shopping & Retail"),
    ("TATA CLIQ ONLINE ORDER", "Shopping & Retail"),
    ("MEESHO RESELLER ORDER", "Shopping & Retail"),
    ("FIRSTCRY BABY PRODUCTS", "Shopping & Retail"),
    ("NETFLIX.COM SUBSCRIPTION", "Entertainment & Recreation"),
    ("BOOKMYSHOW-PVR CINEMAS", "Entertainment & Recreation"),
    ("SPOTIFY PREMIUM AUTOPAY", "Entertainment & Recreation"),
    ("HOTSTAR DISNEY SUB", "Entertainment & Recreation"),
    ("GAMEZOP ENT PVT LTD", "Entertainment & Recreation"),
    ("PVR CINEMAS TICKET BKG", "Entertainment & Recreation"),
    ("INOX MOVIE TICKET", "Entertainment & Recreation"),
    ("YOUTUBE PREMIUM SUB", "Entertainment & Recreation"),
    ("SONYLIV STREAMING SUB", "Entertainment & Recreation"),
    ("ZEE5 SUBSCRIPTION FEE", "Entertainment & Recreation"),
    ("PLAYSTATION STORE WALLET", "Entertainment & Recreation"),
    ("STEAM GAME PURCHASE", "Entertainment & Recreation"),
    ("APPLE MUSIC MONTHLY", "Entertainment & Recreation"),
    ("AMAZON PRIME VIDEO SUB", "Entertainment & Recreation"),
    ("TIMEZONE ARCADE GAMING", "Entertainment & Recreation"),
    ("APOLLO PHARMACY BILL", "Healthcare & Medical"),
    ("PRACTO CONSULT FEE", "Healthcare & Medical"),
    ("1MG ONLINE MEDS ORDER", "Healthcare & Medical"),
    ("FORTIS HOSPITAL OPD", "Healthcare & Medical"),
    ("MEDPLUS HEALTH SERVICES", "Healthcare & Medical"),
    ("PHARMEASY MEDICINE ORDER", "Healthcare & Medical"),
    ("MAX HEALTHCARE OPD FEE", "Healthcare & Medical"),
    ("MANIPAL HOSPITAL BILL", "Healthcare & Medical"),
    ("CULT FIT MEMBERSHIP FEE", "Healthcare & Medical"),
    ("NETMEDS ONLINE PHARMACY", "Healthcare & Medical"),
    ("CLOUDNINE MATERNITY HOSPITAL", "Healthcare & Medical"),
    ("DENTAL CLINIC CONSULT FEE", "Healthcare & Medical"),
    ("DIAGNOSTIC LAB TEST BILL", "Healthcare & Medical"),
    ("AMBULANCE SERVICE CHARGE", "Healthcare & Medical"),
    ("ENT SPECIALIST CONSULT FEE", "Healthcare & Medical"),
    ("BESCOM ELEC BILL PYMT", "Utilities & Services"),
    ("AIRTEL POSTPAID AUTOPAY", "Utilities & Services"),
    ("ACT FIBERNET BROADBAND", "Utilities & Services"),
    ("MAHANAGAR GAS LTD BILL", "Utilities & Services"),
    ("JIO RECHARGE ONLINE", "Utilities & Services"),
    ("VODAFONE IDEA POSTPAID BILL", "Utilities & Services"),
    ("TATA POWER ELEC BILL", "Utilities & Services"),
    ("BSES RAJDHANI PYMT", "Utilities & Services"),
    ("ADANI ELECTRICITY BILL", "Utilities & Services"),
    ("HATHWAY BROADBAND RENEWAL", "Utilities & Services"),
    ("BWSSB WATER BILL PYMT", "Utilities & Services"),
    ("GAS CYLINDER BOOKING FEE", "Utilities & Services"),
    ("DTH RECHARGE TATA PLAY", "Utilities & Services"),
    ("BROADBAND ANNUAL PLAN", "Utilities & Services"),
    ("MOBILE POSTPAID AUTOPAY", "Utilities & Services"),
    ("SIP MUTUAL FUND-HDFC AMC", "Financial Services"),
    ("CRED CARD BILL PYMT", "Financial Services"),
    ("ZERODHA BROKING CHARGES", "Financial Services"),
    ("LIC PREMIUM AUTO DEBIT", "Financial Services"),
    ("PAYTM WALLET LOAD", "Financial Services"),
    ("GROWW MUTUAL FUND SIP", "Financial Services"),
    ("UPSTOX TRADING CHARGES", "Financial Services"),
    ("ANGEL ONE BROKERAGE FEE", "Financial Services"),
    ("GOOGLE PAY WALLET TOPUP", "Financial Services"),
    ("PHONEPE UPI TRANSFER FEE", "Financial Services"),
    ("ICICI DIRECT DEMAT CHARGES", "Financial Services"),
    ("INSURANCE PREMIUM AUTODEBIT", "Financial Services"),
    ("CREDIT CARD EMI AUTO PAY", "Financial Services"),
    ("HOME LOAN EMI AUTO DEBIT", "Financial Services"),
    ("NPS CONTRIBUTION SIP DEBIT", "Financial Services"),
    ("NEFT-SALARY-INFOSYS LTD", "Income"),
    ("IMPS CR-FREELANCE PYMT", "Income"),
    ("SALARY CREDIT-TCS LTD", "Income"),
    ("UPI-CR-CLIENT INVOICE", "Income"),
    ("BONUS PAYOUT-Q3 2026", "Income"),
    ("SALARY CREDIT WIPRO LTD", "Income"),
    ("SALARY CREDIT ACCENTURE", "Income"),
    ("SALARY CREDIT HCL TECH", "Income"),
    ("CONSULTING FEE CREDIT NEFT", "Income"),
    ("REIMBURSEMENT CREDIT TRAVEL", "Income"),
    ("IMPS CR FREELANCE PROJECT", "Income"),
    ("DIVIDEND CREDIT SHARES", "Income"),
    ("INTEREST CREDIT SAVINGS AC", "Income"),
    ("RENTAL INCOME CREDIT", "Income"),
    ("REFUND CREDIT VENDOR PYMT", "Income"),
    ("INCOME TAX REFUND ADJ", "Government & Legal"),
    ("MUNICIPAL PROPERTY TAX", "Government & Legal"),
    ("PASSPORT SEVA FEE PYMT", "Government & Legal"),
    ("RTO VEHICLE REG FEE", "Government & Legal"),
    ("COURT FILING FEE PYMT", "Government & Legal"),
    ("GST PAYMENT CHALLAN", "Government & Legal"),
    ("EPFO CONTRIBUTION PYMT", "Government & Legal"),
    ("E-CHALLAN TRAFFIC FINE", "Government & Legal"),
    ("AADHAAR ENROLLMENT FEE", "Government & Legal"),
    ("STAMP DUTY REGISTRATION", "Government & Legal"),
    ("MUNICIPAL WATER TAX BILL", "Government & Legal"),
    ("PAN CARD APPLICATION FEE", "Government & Legal"),
    ("VEHICLE FITNESS CERT FEE", "Government & Legal"),
    ("PROPERTY REGISTRATION FEE", "Government & Legal"),
    ("LEGAL NOTARY SERVICE FEE", "Government & Legal"),
    ("UPI-DONATION-CRY NGO", "Charity & Donations"),
    ("GIVEINDIA FOUNDATION", "Charity & Donations"),
    ("PM CARES FUND CONTRIB", "Charity & Donations"),
    ("AKSHAY PATRA DONATION", "Charity & Donations"),
    ("RED CROSS SOC INDIA", "Charity & Donations"),
    ("GOONJ NGO DONATION", "Charity & Donations"),
    ("HELPAGE INDIA CONTRIB", "Charity & Donations"),
    ("SAVE THE CHILDREN DONATE", "Charity & Donations"),
    ("SMILE FOUNDATION DONATION", "Charity & Donations"),
    ("TEMPLE DONATION HUNDI", "Charity & Donations"),
    ("ANIMAL WELFARE TRUST DONATION", "Charity & Donations"),
    ("ORPHANAGE CHARITY FUND", "Charity & Donations"),
    ("DISASTER RELIEF FUND DONATE", "Charity & Donations"),
    ("NGO CSR CONTRIBUTION", "Charity & Donations"),
    ("FLOOD RELIEF FUND DONATION", "Charity & Donations"),
]


def evaluate(predict_fn) -> dict:
    """predict_fn(description: str) -> (category, confidence). Returns a
    summary dict — accuracy, macro/weighted F1, per-category
    precision/recall/F1, average confidence, and every misclassified
    example — suitable for embedding directly in metrics.json.

    Accuracy alone is misleading on a multi-class problem: with 10
    categories and only 5 examples each here, a model that's strong on
    common categories and weak on rare ones can post a deceptively good
    accuracy while failing entire categories. Macro-F1 (unweighted mean
    across categories) surfaces that; the held-out split already reports
    it (see selected_model_full_report in metrics.json) — this stress
    test should too, for the same reason.
    """
    from sklearn.metrics import classification_report

    results = []
    for description, true_category in REALISTIC_EXAMPLES:
        predicted_category, confidence = predict_fn(description)
        results.append(
            {
                "description": description,
                "expected": true_category,
                "predicted": predicted_category,
                "confidence": confidence,
                "correct": predicted_category == true_category,
            }
        )

    n = len(results)
    correct = sum(r["correct"] for r in results)
    y_true = [r["expected"] for r in results]
    y_pred = [r["predicted"] for r in results]
    # zero_division=0: a category the model never predicts here (n=5 per
    # category, so possible) would otherwise raise/warn on undefined
    # precision — 0 is the honest score for "never got this one right."
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)

    return {
        "num_examples": n,
        "accuracy": correct / n,
        "macro_f1": report["macro avg"]["f1-score"],
        "macro_precision": report["macro avg"]["precision"],
        "macro_recall": report["macro avg"]["recall"],
        "weighted_f1": report["weighted avg"]["f1-score"],
        "average_confidence": sum(r["confidence"] for r in results) / n,
        "per_category": {k: v for k, v in report.items() if k not in ("accuracy",)},
        "misclassified": [r for r in results if not r["correct"]],
    }


def main() -> None:
    """CLI entry point — loads whatever model is currently saved on disk
    via the backend service and prints a readable report."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.services.expense_categorization_service import predict_category

    def predict_fn(description: str):
        result = predict_category(description)
        if result is None:
            raise RuntimeError("Model not available — run train_expense_categorizer.py first.")
        return result

    summary = evaluate(predict_fn)

    for description, true_category in REALISTIC_EXAMPLES:
        predicted_category, confidence = predict_fn(description)
        marker = "OK" if predicted_category == true_category else "WRONG"
        print(
            f"[{marker:5}] {description!r:40} -> {predicted_category:28} "
            f"({confidence:.1%})  [expected: {true_category}]"
        )

    print(f"\n{'=' * 70}")
    print(f"Realistic-text accuracy: {summary['accuracy']:.1%} ({summary['num_examples']} examples)")
    print(f"Macro F1: {summary['macro_f1']:.4f}  |  Macro precision: {summary['macro_precision']:.4f}  |  Macro recall: {summary['macro_recall']:.4f}")
    print(f"Weighted F1: {summary['weighted_f1']:.4f}")
    print(f"Average confidence: {summary['average_confidence']:.1%}")
    if summary["misclassified"]:
        print(f"\nMisclassified ({len(summary['misclassified'])}):")
        for r in summary["misclassified"]:
            print(f"  {r['description']!r} -> got {r['predicted']!r} ({r['confidence']:.1%}), expected {r['expected']!r}")


if __name__ == "__main__":
    main()
