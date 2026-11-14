import json

def create_new_tid_from_template(
	title: str,
	caption: str,
	text: str,
	tags: list[str] = None,
	modified: str = None,
	created: str = None,
	creator: str = None,
	fields: dict = None,
) -> dict:
	"""
	Create a new TID from the template.

	Args:
		title (str): The title of the TID.
		caption (str): The caption of the TID.
		text (str): The text of the TID.
		tags (list[str], optional): The tags for the TID. Defaults to None.
		modified (str, optional): The modified date of the TID. Defaults to None.
		created (str, optional): The created date of the TID. Defaults to None.
		creator (str, optional): The creator of the TID. Defaults to None.
		field (dict, optional): The field to add to the TID. Defaults to None.

	Returns:
		dict: The new TID.
	"""
	temp_tid = {}
	temp_tid['title'] = title
	temp_tid['caption'] = caption
	temp_tid['text'] = text
	if tags:
		temp_tid['tags'] = tags
	if modified:
		temp_tid['modified'] = modified
	if created:
		temp_tid['created'] = created
	if creator:
		temp_tid['creator'] = creator
	if fields:
		for field, value in fields.items():
			temp_tid[field] = value

	return temp_tid

def append_tid_for_output(input, output):
	output.append(input)
	print(input['title']+'.tid has been created.')

def write_tid_list_to_json(tid_list: list, output_filename: str) -> None:
	"""
	Write the list of tid files to a json file

	Args:
		tid_list (list): The list of tid files.
		output_filename (str): The name of the output file.

	Returns:
		None
	"""
	with open(output_filename, 'w') as outfile:
		json.dump(tid_list, outfile, indent=4, sort_keys=True)
		
