"""Describe requested NHGIS tables or boundaries and check what NHGIS prepared against them."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..http_transport import DataProviderError
from ..raw_file_requests import NhgisBoundaryFileRequest, NhgisTableFileRequest


class NhgisDatasetSelection(BaseModel):
    """Choose tables and geographic levels from one named NHGIS dataset.

    A dataset combines a Census year and source, such as 1980_STF1. Geographic levels select kinds
    of areas, such as counties; they do not identify particular counties or tracts.

    Attributes:
        tables (tuple[str, ...]): One or more NHGIS table identifiers, such as "NT7".
        geographic_levels (tuple[str, ...]): NHGIS codes for kinds of areas, such as "county" or
            "tract_080". Defaults to ().
        years (tuple[str, ...]): Census years as strings, such as "1980". Defaults to ().
        breakdowns (tuple[str, ...]): Codes selecting whole areas or their subareas, such as
            "bs03.ge0000" for the whole area in 1980_STF1. Defaults to ().

    When checking a completed request, empty years and breakdowns mean the Census year and whole
    area for 1980_STF1 and 1990_STF1. This code supplies no such defaults for other datasets. The
    selections are sent to NHGIS as written; NHGIS checks whether the codes exist.
    """

    # NOTE: NHGIS calls these fields dataTables, geogLevels, and breakdownValues.
    # Validation aliases read those names; serialization aliases write them in requests and saved
    # definitions. validate_by_name also lets Python callers use our readable field names. Reject
    # unknown fields and prevent reassignment.
    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_by_name=True, validate_by_alias=True
    )
    tables: tuple[str, ...] = Field(
        validation_alias="dataTables", serialization_alias="dataTables", min_length=1
    )
    geographic_levels: tuple[str, ...] = Field(
        default=(),
        validation_alias="geogLevels",
        serialization_alias="geogLevels",
    )
    years: tuple[str, ...] = ()
    breakdowns: tuple[str, ...] = Field(
        default=(), validation_alias="breakdownValues", serialization_alias="breakdownValues"
    )


class NhgisExtractDefinition(BaseModel):
    """Selections sent to NHGIS, saved locally, and compared with the completed request.

    An extract is a package NHGIS prepares from selected tables or boundary files. Each request
    must select one of those two kinds, not both. Time-series tables are not supported. Optional
    settings left out of the definition are also left out of the request sent to NHGIS.

    Attributes:
        collection (Literal["nhgis"]): Identifies the NHGIS service, always "nhgis".
        description (str): Optional label sent to NHGIS. Defaults to an empty string.
        version (int | None): Version metadata accepted in NHGIS responses. Defaults to None.
            Retrieval does not select or compare versions.
        datasets (dict[str, NhgisDatasetSelection]): Dataset names, such as "1980_STF1", mapped to
            table selections. Defaults to {}; cannot be used together with shapefiles.
        shapefiles (tuple[str, ...]): NHGIS shapefile identifiers, such as
            "us_county_1980_tl2008". Defaults to (); cannot be used together with datasets.
        geographic_extents (tuple[str, ...]): NHGIS codes limiting which areas a table covers.
            Defaults to (); NHGIS interprets the codes.
        data_format (Literal["csv_header", "csv_no_header"] | None): Both include column names;
            csv_header also includes a second row of full descriptions. Defaults to None; an
            omitted setting leaves the provider's default in effect.
        data_layout (Literal["single_file"] | None): Combine breakdowns and data types within each
            dataset/geography file. Does not combine different geography levels into one file.
            Defaults to None; NHGIS may omit it when there is nothing to split or combine.
        time_series_tables (dict[str, str]): Must remain empty because these requests are
            unsupported. Defaults to {}.
        time_series_layout (str | None): Layout metadata accepted in NHGIS responses. Defaults to
            None. Retrieval does not select or compare it; time-series tables are unsupported.

    NOTE: Aliases let Python use readable names while NHGIS uses its required API names: for
    example, data_layout corresponds to breakdownAndDataTypeLayout. Both directions are needed:
    validation aliases read responses and saved definitions; serialization aliases write requests
    and saved definitions when by_alias=True is used.
    """

    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_by_name=True, validate_by_alias=True
    )
    collection: Literal["nhgis"] = "nhgis"
    description: str = ""
    version: int | None = None
    datasets: dict[str, NhgisDatasetSelection] = Field(default_factory=dict)
    shapefiles: tuple[str, ...] = ()
    geographic_extents: tuple[str, ...] = Field(
        default=(), validation_alias="geographicExtents", serialization_alias="geographicExtents"
    )
    data_format: Literal["csv_header", "csv_no_header"] | None = Field(
        default=None, validation_alias="dataFormat", serialization_alias="dataFormat"
    )
    data_layout: Literal["single_file"] | None = Field(
        default=None,
        validation_alias="breakdownAndDataTypeLayout",
        serialization_alias="breakdownAndDataTypeLayout",
    )
    time_series_tables: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="timeSeriesTables",
        serialization_alias="timeSeriesTables",
        max_length=0,
    )
    time_series_layout: str | None = Field(
        default=None,
        validation_alias="timeSeriesTableLayout",
        serialization_alias="timeSeriesTableLayout",
    )

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        """Require tables or boundary files, raising ValueError when both or neither are selected."""
        if self.datasets and self.shapefiles:
            raise ValueError("Request either NHGIS datasets or shapefiles, not both")
        if not self.datasets and not self.shapefiles:
            raise ValueError("Request either NHGIS datasets or shapefiles")

        return self

    def to_provider_request(self) -> dict[str, object]:
        """Build the dictionary to send to NHGIS, using the names its service expects.

        The collection name is always included. Optional settings that were not supplied remain
        absent, allowing NHGIS to apply its defaults.
        """
        return {
            "collection": self.collection,
            **self.model_dump(mode="json", by_alias=True, exclude_unset=True),
        }


class NhgisDownloadLink(BaseModel):
    """A temporary download address used during retrieval and never saved in a submission record.

    Attributes:
        url (str): Provider download URL, which may contain an access token in the address itself.
    """

    model_config = ConfigDict(extra="ignore")
    url: str


class NhgisExtractResponse(BaseModel):
    """NHGIS's description of the prepared data and the temporary addresses for downloading it.

    Attributes:
        request_definition (NhgisExtractDefinition): Selections NHGIS reports as
            extractDefinition. Compare these with the original request before downloading.
        download_links (dict[str, NhgisDownloadLink]): Download addresses named by content type:
            tableData for tables or gisData for boundaries. Retrieval fails if its required link
            is absent.

    Extra response fields are ignored. Do not save this response in a submission record because
    its download addresses may themselves grant temporary access to the files.

    NOTE: This model only reads responses, so retrieval needs its validation aliases but does not
    use its serialization aliases. These translate extractDefinition and downloadLinks into the
    Python attributes described above.
    """

    model_config = ConfigDict(extra="ignore", validate_by_name=True, validate_by_alias=True)
    request_definition: NhgisExtractDefinition = Field(
        validation_alias="extractDefinition", serialization_alias="extractDefinition"
    )
    download_links: dict[str, NhgisDownloadLink] = Field(
        validation_alias="downloadLinks", serialization_alias="downloadLinks"
    )


def build_nhgis_definition(
    request: NhgisTableFileRequest | NhgisBoundaryFileRequest,
) -> NhgisExtractDefinition:
    """Turn a raw-file request into the selections NHGIS needs to prepare a download.

    Table requests ask for column names and descriptions in the CSV and keep breakdowns together
    within each dataset/geography file. The dataset supplies its default year. Boundary requests
    select only the named shapefiles.

    Args:
        request (NhgisTableFileRequest | NhgisBoundaryFileRequest): Versioned table or boundary
            selection from the raw-input definitions.

    Returns:
        NhgisExtractDefinition: Selections used both for submission and for checking the result.
    """
    if isinstance(request, NhgisBoundaryFileRequest):
        return NhgisExtractDefinition(shapefiles=request.shapefiles)

    selection = NhgisDatasetSelection(
        tables=request.tables,
        geographic_levels=request.geographic_levels,
        breakdowns=request.breakdowns,
    )
    return NhgisExtractDefinition(
        description=request.description,
        datasets={request.dataset_name: selection},
        data_format="csv_header",
        data_layout="single_file",
    )


def validate_nhgis_definition(
    actual: NhgisExtractDefinition, requested: NhgisExtractDefinition
) -> None:
    """Check that NHGIS prepared the requested tables, boundaries, and geographic selections.

    NHGIS can describe the same selection differently by reordering lists, reporting defaults, or
    omitting an irrelevant layout setting. These allowances prevent rejecting matching extracts;
    they do not allow changes to the selected data. See
    documentation/raw_source_acquisition.md#nhgis-request-comparisons for examples.

    Reordered selections count as a match. For 1980/1990 STF1, omitted years and area breakdowns
    are compared using the known Census-year and whole-area defaults. Data format and layout are
    checked only when requested. An omitted layout is accepted for 1980/1990 STF1 selections with
    only one breakdown per dataset, since these datasets have only one data type. Version metadata
    is not compared because retrieval does not select a version; this does not establish
    equivalence between versions. Time-series layout is ignored because those tables are not
    requested.

    Args:
        actual (NhgisExtractDefinition): Definition returned by NHGIS for the completed extract.
        requested (NhgisExtractDefinition): Original request retained with the submission.

    Raises:
        DataProviderError: Dataset, table, geography, or requested output selections differ.
    """
    if requested.data_format is not None and actual.data_format != requested.data_format:
        raise DataProviderError("NHGIS changed the requested data_format")

    if (
        requested.data_layout is not None
        and actual.data_layout != requested.data_layout
        and (actual.data_layout is not None or not can_omit_data_layout(requested))
    ):
        raise DataProviderError("NHGIS changed the requested data_layout")

    if set(actual.shapefiles) != set(requested.shapefiles):
        raise DataProviderError("NHGIS changed the requested shapefiles")

    if set(actual.geographic_extents) != set(requested.geographic_extents):
        raise DataProviderError("NHGIS changed the requested geographic extents")

    if actual.datasets.keys() != requested.datasets.keys():
        raise DataProviderError("NHGIS changed the requested datasets")

    for dataset_name, selection in requested.datasets.items():
        requested_selection = resolve_dataset_defaults(dataset_name, selection)
        actual_selection = resolve_dataset_defaults(dataset_name, actual.datasets[dataset_name])

        validate_dataset_selection(actual_selection, requested_selection)


def can_omit_data_layout(definition: NhgisExtractDefinition) -> bool:
    """Whether each dataset has just one breakdown and one data type, making layout irrelevant.

    NHGIS metadata reports hasMultipleDataTypes=false for 1980_STF1 and 1990_STF1. Omitted
    breakdown selections use their single whole-area default. Other datasets require an explicit
    layout because their data types have not been established here. See
    documentation/raw_source_acquisition.md#nhgis-table-layout for the source references.

    Args:
        definition (NhgisExtractDefinition): Table selections whose layout is being compared.

    Returns:
        bool: True only for known STF1 datasets with at most one selected breakdown each.
    """
    return bool(definition.datasets) and all(
        dataset_name in ("1980_STF1", "1990_STF1") and len(selection.breakdowns) <= 1
        for dataset_name, selection in definition.datasets.items()
    )


def validate_dataset_selection(
    actual: NhgisDatasetSelection, requested: NhgisDatasetSelection
) -> None:
    """Require matching table and area selections, regardless of the order NHGIS lists them.

    Call resolve_dataset_defaults() on both selections first so an omitted default and an
    explicitly named default count as the same request.

    Args:
        actual (NhgisDatasetSelection): NHGIS's completed selections with known defaults filled
            in.
        requested (NhgisDatasetSelection): Original selections with those same defaults filled in.

    Raises:
        DataProviderError: A selected table, geographic level, year, or breakdown differs.
    """
    if set(actual.tables) != set(requested.tables):
        raise DataProviderError("NHGIS changed the requested dataset tables")

    if set(actual.geographic_levels) != set(requested.geographic_levels):
        raise DataProviderError("NHGIS changed the requested dataset geographies")

    if set(actual.years) != set(requested.years):
        raise DataProviderError("NHGIS changed the requested dataset years")

    if set(actual.breakdowns) != set(requested.breakdowns):
        raise DataProviderError("NHGIS changed the requested dataset breakdowns")


def resolve_dataset_defaults(
    dataset_name: str, selection: NhgisDatasetSelection
) -> NhgisDatasetSelection:
    """Fill omitted years and area breakdowns for comparing 1980/1990 STF1 selections.

    NHGIS may report a default explicitly even when the request left it out. For these two
    datasets, use the dataset's Census year and whole-area code so those forms compare equally.
    Other datasets and explicit selections are unchanged. The original object is never modified.

    Args:
        dataset_name (str): NHGIS dataset identifier used to select known defaults.
        selection (NhgisDatasetSelection): Selections being checked. Filled defaults are for
            comparison only, not for changing the request sent to NHGIS.

    Returns:
        NhgisDatasetSelection: Selections with known empty years and breakdowns filled in.
    """
    dataset_defaults = {"1980_STF1": ("1980", "bs03.ge0000"), "1990_STF1": ("1990", "bs09.ge00")}
    if dataset_name not in dataset_defaults:
        return selection

    census_year, total_area_code = dataset_defaults[dataset_name]

    return selection.model_copy(
        update={
            "years": selection.years or (census_year,),
            "breakdowns": selection.breakdowns or (total_area_code,),
        }
    )
