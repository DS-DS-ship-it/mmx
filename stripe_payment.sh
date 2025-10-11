#!/bin/bash

AMOUNT=36000                     # total charge in cents ($360.00)
FEE=1000                         # platform/app fee in cents ($10.00)
DESTINATION="acct_1SGxNyGsEENWPdha"

stripe payment_intents create \
  -d amount=$AMOUNT \
  -d currency=usd \
  -d payment_method=pm_card_visa \
  -d confirm=true \
  -d application_fee_amount=$FEE \
  -d transfer_data[destination]=$DESTINATION \
  -d payment_method_types[]=card
