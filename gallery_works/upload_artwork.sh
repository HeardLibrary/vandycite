python3 ../../linked-data/commonsbot/commonstool.py --config image_upload/commonstool_config.yml
python3 ../../linked-data/commonsbot/transfer_to_vanderbot.py --config image_upload/commonstool_config.yml
python3 ../../linked-data/vanderbot/vanderbot.py --log error_log.txt --terse true
