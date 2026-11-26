"""Phase 4 stock prediction: feature, horizon and distribution maths.

Pure functions with no database or network access, shared by the offline
training script (ml/train_stock_predictor.py) and the daily prediction job,
so both compute features exactly the same way.
"""
