# -*- coding: utf-8 -*-
"""Collects Timesketch events."""
import datetime
import tempfile
from typing import List

import pandas as pd
from timesketch_api_client import client
from timesketch_api_client import search
from timesketch_api_client import sketch

from dftimewolf.lib import module
from dftimewolf.lib import state as state_lib
from dftimewolf.lib import timesketch_utils
from dftimewolf.lib.containers import containers
from dftimewolf.lib.modules import manager as modules_manager


_VALID_OUTPUT_FORMATS = frozenset(['csv', 'json', 'jsonl', 'pandas'])


class TimesketchSearchEventCollector(module.BaseModule):
  """Collector for Timesketch events.

  Collects Timesketch events using given search.

  Attributes:
    query_string: the Timesketch query string.
    start_datetime: the start datetime.
    end_datetime: the end datetime.
    indices: the list of Timesketch indices.
    labels: the Timesketch labels.
    output_format: the output format.
    return_fields: the comma-separated Timesketch return fields.
    search_name: an optional name for the search.
    search_description: an optional description for the search.
    include_internal_columns: show Timesketch internal columns.
    sketch_id: the Timesketch sketch ID.
    sketch: the Timesketch sketch.
  """

  def __init__(
      self,
      state: state_lib.DFTimewolfState,
      name: str | None = None,
      critical: bool = False
  ) -> None:
    """"""
    super(TimesketchSearchEventCollector, self).__init__(
        state, name=name, critical=critical)
    self.query_string: str = ''
    self.start_datetime: datetime.datetime | None = None
    self.end_datetime: datetime.datetime | None = None
    self.indices: List[int] = []
    self.labels: List[str] = []
    self.output_format: str = ''
    self.return_fields: str = ''
    self.search_name: str = ''
    self.search_description: str = ''
    self.include_internal_columns: bool = False
    self.sketch_id: int = 0
    self.sketch: sketch.Sketch | None = None

  # pylint: disable=arguments-differ,too-many-arguments
  def SetUp(
      self,
      sketch_id: str | None = None,
      query_string: str = '*',
      start_datetime: datetime.datetime | None = None,
      end_datetime: datetime.datetime | None = None,
      indices: str | None = None,
      labels: str | None = None,
      output_format: str = 'pandas',
      return_fields: str = '*',
      search_name: str | None = None,
      search_description: str | None = None,
      include_internal_columns: bool = False,
      token_password: str = '',
      endpoint: str | None = None,
      username: str | None = None,
      password: str | None = None
  ) -> None:
    """Sets up the TimesketchSearchEventCollector.

    Args:
      sketch_id: the Timesketch sketch ID.  Defaults to the value
          in the ticket attribute container.
      query_string: the query string.  Defaults to '*' (all events).
      start_datetime: the start datetime.
      end_datetime: the end datetime.
      indices: the comma-separated Timesketch indices.
      labels: the comma-separated Timesketch event labels.
      output_format: the output format.  Defaults to 'pandas'.
      return_fields: the return fields.  Defaults to '*'.
      search_name: an optional name for the search.
      search_description: an optional description for the search.
      include_internal_columns: include Timesketch internal columns.  Defaults
          to False.
      token_password: optional password used to decrypt the
          Timesketch credential storage. Defaults to an empty string since
          the upstream library expects a string value. An empty string means
          a password will be generated by the upstream library.
      endpoint: Timesketch server URL (e.g. http://localhost:5000/).
          Optional when token_password is provided.
      username: Timesketch username. Optional when token_password is provided.
      password: Timesketch password. Optional when token_password is provided.
    """
    if not sketch_id:
      attributes = self.GetContainers(containers.TicketAttribute)
      self.sketch_id = timesketch_utils.GetSketchIDFromAttributes(attributes)
      if not self.sketch_id:
        self.ModuleError(
            'Sketch ID is not set and not found in ticket attributes.',
            critical=True)
    else:
      self.sketch_id = int(sketch_id)

    if not start_datetime or not end_datetime:
      self.ModuleError(
          'Both the start and end datetime must be set.', critical=True)

    if output_format not in _VALID_OUTPUT_FORMATS:
      self.ModuleError(
          f'Output format not one of {",".join(_VALID_OUTPUT_FORMATS)}',
          critical=True)

    self.sketch = self._GetSketch(token_password, endpoint, username, password)
    self.start_datetime = start_datetime
    self.end_datetime = end_datetime
    self.query_string = query_string
    self.return_fields = return_fields
    self.output_format = output_format
    self.include_internal_columns = include_internal_columns

    if labels:
      self.labels = [label.strip() for label in labels.split(',')]

    if indices:
      self.indices = [int(index) for index in indices.split(',')]

    if search_name:
      self.search_name = search_name

    if search_description:
      self.search_description = search_description

  def _GetSketch(
      self,
      token_password: str | None = None,
      endpoint: str | None = None,
      username: str | None = None,
      password: str | None = None
  ) -> sketch.Sketch:
    """Gets the Timesketch sketch.

    Args:
      token_password: optional password used to decrypt the
          Timesketch credential storage. Defaults to an empty string since
          the upstream library expects a string value. An empty string means
          a password will be generated by the upstream library.
      endpoint: Timesketch server URL (e.g. http://localhost:5000/).
          Optional when token_password is provided.
      username: Timesketch username. Optional when token_password is provided.
      password: Timesketch password. Optional when token_password is provided.

    Returns:
      The Timesketch sketch.
    """
    if endpoint and username and password:
      timesketch_api = client.TimesketchApi(endpoint, username, password)
    elif token_password:
      timesketch_api = timesketch_utils.GetApiClient(
          self.state, token_password=token_password)
    else:
      timesketch_api = timesketch_utils.GetApiClient(self.state)

    if not timesketch_api:
      self.ModuleError(
          'Unable to get a Timesketch API client, try deleting the files '
          '~/.timesketchrc and ~/.timesketch.token',
          critical=True)
    if not timesketch_api.session:
      self.ModuleError('Could not connect to Timesketch server.', critical=True)

    sketch_obj = timesketch_api.get_sketch(self.sketch_id)
    if not sketch_obj:
      self.ModuleError(f'Could not get sketch {self.sketch_id}', critical=True)
    self.state.AddToCache('timesketch_sketch', sketch_obj)
    return sketch_obj

  def _GetSearchResults(self) -> pd.DataFrame:
    """Get the Timesketch search results.

    Returns:
      the results in a Pandas dataframe.
    """
    search_obj = search.Search(self.sketch)
    search_obj.query_string = self.query_string
    search_obj.return_fields = self.return_fields
    if self.indices:
      search_obj.indices = self.indices

    if self.start_datetime and self.end_datetime:
      range_chip = search.DateRangeChip()
      range_chip.add_start_time(
          self.start_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f'))
      range_chip.add_end_time(
          self.end_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f'))
      search_obj.add_chip(range_chip)

    for label in self.labels:
      label_chip = search.LabelChip()
      if label == "star":
        label_chip.use_star_label()
      elif label == "comment":
        label_chip.use_comment_label()
      else:
        label_chip.label = label
      search_obj.add_chip(label_chip)
    return search_obj.to_pandas()

  def _OutputSearchResults(self, data_frame: pd.DataFrame) -> None:
    """Outputs the search results.

    Args:
      data_frame: the dataframe containing the Timesketch events.
    """
    if not self.include_internal_columns:
      # Remove internal OpenSearch columns
      data_frame = data_frame.drop(
          columns=["__ts_timeline_id", "_id", "_index", "_source", "_type"],
          errors="ignore")

    if self.output_format == 'pandas':
      self.StoreContainer(
          containers.DataFrame(
              name=self.search_name,
              description=self.search_description,
              data_frame=data_frame))
    else:
      with tempfile.NamedTemporaryFile(
          mode='w',
          delete=False,
          encoding='utf-8',
          prefix=f'{self.search_name}_' if self.search_name else '',
          suffix=f'.{self.output_format}') as output_file:
        if self.output_format == "csv":
          data_frame.to_csv(output_file, index=False)
        elif self.output_format == "json":
          data_frame.to_json(output_file, orient="records", lines=False)
        elif self.output_format == "jsonl":
          data_frame.to_json(output_file, orient="records", lines=True)
        else:
          self.ModuleError('Unexpected output format', critical=True)
        self.StoreContainer(containers.File(
            name=self.search_name,
            description=self.search_description,
            path=output_file.name))

  def Process(self) -> None:
    """Processes the Timesketch search query."""
    data_frame = self._GetSearchResults()
    self.logger.info(f'Search returned {len(data_frame)} event(s).')
    if data_frame.empty:
      return
    self._OutputSearchResults(data_frame)


modules_manager.ModulesManager.RegisterModule(TimesketchSearchEventCollector)
