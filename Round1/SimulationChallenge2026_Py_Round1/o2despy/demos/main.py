import datetime
import time

from o2des.config import Config

from o2des.utils import LogUtils

from .demo1.hello_world import HelloWorld

if __name__ == '__main__':
    run_code = 'O2DESPy'
    start_time = time.time()

    logger = LogUtils.get_logger()

    logger.debug("Init time: {}".format(time.time() - start_time))
    logger.critical('Run: {}'.format(run_code))
    logger.update_config(
        file_path=Config.log_file_path,
        dynamic=True,
        include_log=['debug', 'info', 'warning', 'error', 'critical'],
        name=run_code,
        stream_level='critical',
        output_mode=['stream', 'file'],
        file_level='debug',
        fmt='%(levelname)s: %(message)s')

    # Demo 1
    logger.info("Demo 1 - Hello world")
    sim1 = HelloWorld(10, seed=3)
    hc1 = sim1.add_hour_counter()
    sim1.warmup(till=datetime.datetime(year=1, month=1, day=1, hour=0, minute=5))
    # sim1.run(event_count=10)
    # sim1.run(speed=10)
    # sim1.run(terminate=datetime.datetime(year=1, month=1, day=1, hour=0, minute=5))
    sim1.run(duration=datetime.timedelta(seconds=30))
    logger.critical('use time {}'.format(time.time() - start_time))


