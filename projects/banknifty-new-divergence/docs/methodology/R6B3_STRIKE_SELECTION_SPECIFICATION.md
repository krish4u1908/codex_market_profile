# R6B3 strike selection

At each causal observation time, select the nearest non-expired expiry physically present in that receipt-time chain. Determine ATM as the listed strike nearest the latest causal BankNifty index price, resolving a tie to the lower strike. Preserve ATM and up to three listed strikes on either side. Moneyness is recomputed separately for CE and PE. Missing strikes are not synthesized and expiries are never pooled.
