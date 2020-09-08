# Repository for the VandyCite project

Note: this is a private repository, so the data here won't be exposed publicly unless the repo settings are changed.

## Notes on running the download script

The default file locations assume that you have cloned both the `linked-data` and `vandycite` repos into the same directory. If so, the input file (CSV containing the Q IDs in a column with header `qid`) and output files will be put into a subdirectory of `vandycite` as specified in line 18 of the first cell. 

The properties to be downloaded are controlled by the items in the `prop_list` list. The `variable` value MUST NOT have spaces. Use underscores between words.

If the flag `manage_labels_descriptions` is `True`, the label and description column will follow immediately after the `qid` column and making changes to either field will result in changing the metadata on Wikidata. If the flag `manage_labels_descriptions` is `False`, the label will be the last column in the spreadsheet and will be ignored by VanderBot. The description will not be given. In this situation, the purpose of the label is simply to make it easier to know what the subject of the row is.

There are three fixed reference properties that the download script uses (stated in, reference URL, and retrieved). For how I determined that, see the notes with [this script](https://github.com/HeardLibrary/linked-data/blob/master/publications/divinity-law/determine_ref_properties.ipynb). 

## Notes on editing CSVs for upload by VanderBot

**Note:** the data download script currently does not support qualifiers. However, VanderBot can write qualifiers as long as they are associated with a new statement. In cases where values of a property need qualifiers, we should talk about how to handle that.

Items are unordered. They can be sorted in any way using a spreadsheet program. The order of lines does not matter to Vanderbot.

Do not change with the column headings, nor change the order of the columns without adjusting the corresponding `csv-metadata.json` file. If you don't know what this means, then don't change either of these things.

### Duplicate rows
The spreadsheet called `something-multiprop.csv` contains columns for all of the properties that would be expected to have only a single value. Thus there should not be two rows for the same item. If there is, it may be because there is something weird like two references that have overlapping data. Sometimes there are just duplicate statements. It is best to look at the actual item record to try to figure out what is going on. The extra reference can be deleted and then after enough time has passed for the Query Service to be updated, the script can be run again.

The other spreadsheets called something like `something-propertyname.csv` have only a single property that could have multiple values per item. Thus we would expect multiple rows for the same item. Howver, if the rows seem identical, they could be duplicated for a similar reason to what was just described above.

In the case where values are language-tagged strings (like titles), the language tags aren't automatically downloaded. This is something the download script might handle in the future.

NOTE: Take a look at https://www.wikidata.org/wiki/Q50426286 for example of duplicated ISSN reference. Also talk about how to handle ISSNs for different formats.

### Levels of writing

There are three levels where new data can be written to Wikidata:

1. An entirely new item.
2. A new statement about an existing item.
3. A new reference about an existing statement.

Each level writes all data at a lower level. A new item writes all statements and references whose data are on a row. A new statement for an existing item writes the statement value and all references related to that statement. A new reference for an existing statement adds only that reference.

The three levels have the following kinds of identifiers:
1. An item has a Q ID. For example: `Q15817868`.
2. A statement has a UUID. UUIDs generally are written as five parts separated by dashes. For example: `4dc15168-4537-ee3a-b690-5df46ee19de4`. Although capitalization of UUIDs should not matter, it actually does in Wikidata, so the capitalization of a statement UUID should not be changed.
3. A reference has a hash. A hash is not written with dashes. For example: `5684f0c6e66933dafb26b3f932ab13cbeae7bccf`. Typically, in Wikidata most hashes are in lower case. But don't mess with capitalization of them.

There is a fourth kind of identifier: dates have node IDs. But these cannot be controlled by you, so you should ignore them.

Here is the general pattern of column headers:
- columns related to the same property begin with the same string. For example, `language_of_work`, `language_of_work_ref1_statedIn`, and `language_of_work_ref1_retrieved_prec` are all related to the "language of work" property.
- columns related to the same reference begin with the same string and have `ref1`, `ref2`, etc. in their string. For example: `language_of_work_ref1_statedIn` and `language_of_work_ref1_retrieved_val` both are related to the same reference for a "language of work" statement.
- there are always three columns for each data. They always have the same beginning string and end with `_nodeid`, `_val` (the date value), and `_prec` (the level of precision with 11=day, 10=month, and 9=year).

Here are the general rules: 
- If an item is new, none of its statements should have UUIDs nor its references hashes. VanderBot knows it should create a new item when the Q ID cell is empty. 
- To add an new statement to an existing item, none of its references should have hashes. VanderBot knows it should create a new statement when a property's UUID cell is empty. 
- To add a new reference to an existing statement, its hash cell should be empty.
- You CANNOT change or delete values. You can only add them. To make changes, use the online editor. The exception to this is labels and descriptions. If the flag `manage_labels_descriptions` was set to `True` and the label and description are in the columns immediately to the right of the `qid` column, then making changes to the value of either will result in a change in Wikidata. If the flag `manage_labels_descriptions` is `False` and the label column is the last column, then changing the label will have no effect at Wikidata.

Because references cannot be changed once written, make sure that you have filled in all of the fields you care about before writing. For example, include both the reference URL and the date retrieved at the same time. Don't write one first and plan to do the other one later. If an existing reference has a reference URL but no retrieved date, try retrieving it and add the date using the web editor.

### Adding data values

Eventually, the `_nodeid`, `_val`, and `_prec` columns will be modified or filled by VanderBot. But you only need to fill in the `_val` column. VanderBot will know the precision of the date by the form of what you type. Use this form:

| precision | date | form |
| --- | --- | --- |
| year | 1973 | 1973 |
| month | March 1854 | 1854-03 |
| day | 7 December 1941 | 1941-12-07 |

Note that the order is yyyy-mm-dd and that months and days less than 10 must have a leading zero. DO NOT try to edit dates in a CSV spreadsheet with Excel! Use Libre Office or Open Office. If the software insists on changing the format of a date, preceed the date with a single quote, like this: `'1941-12-07`. The quote will not be part of the date - it is just a signal to the software that the value should be treated as a string and not interpreted.

----
Last modified 2020-09-07