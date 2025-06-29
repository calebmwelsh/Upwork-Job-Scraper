import logging
import coloredlogs
import os

class Logger:
    # Default directories for each log level
    LOG_DIRS = {
        'DEBUG': os.path.join('data', 'logging', 'states', 'debug'),
        'INFO': os.path.join('data', 'logging', 'states', 'info'),
        'WARNING': os.path.join('data', 'logging', 'states', 'warning'),
        'ERROR': os.path.join('data', 'logging', 'states', 'error'),
        'CRITICAL': os.path.join('data', 'logging', 'states', 'critical'),
    }

    def __init__(self, name="Upwork", level="DEBUG"):
        # Ensure all log directories exist
        for log_dir in self.LOG_DIRS.values():
            os.makedirs(log_dir, exist_ok=True)
        self.logger = logging.getLogger(name)
        self.set_level(level)
        self._setup_coloredlogs()

    def set_level(self, level):
        self.logger.setLevel(level)

    def _setup_coloredlogs(self):
        level_styles = {
            'debug': {'color': 'blue'},
            'info': {'color': 'white'},
            'warning': {'color': 'yellow'},
            'error': {'color': 'red'},
            'critical': {'color': 'red', 'bold': True},
        }
        field_styles = {
            'asctime': {'color': 'white'},
            'name': {'color': 'magenta', 'bold': False},
            'levelname': {'color': 'cyan', 'bold': False},
        }
        coloredlogs.install(
            level=self.logger.level,
            logger=self.logger,
            fmt="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
            level_styles=level_styles,
            field_styles=field_styles
        )

    def get_logger(self):
        return self.logger

    @classmethod
    def get_log_dir(cls, level):
        """
        Get the default directory for a given log level (case-insensitive).
        """
        return cls.LOG_DIRS.get(level.upper(), os.path.join('data', 'logging', 'states', 'other'))