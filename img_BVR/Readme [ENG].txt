############################################
####Program - .img BVR (BatchViewRender)####
#########Program Version 1.0.nt.BREV########
############################################

Author: m0reslav
	moreslav.ru
		https://github.com/R3DCyclops

Processing and parsing of .img files are based on the gtaLib module from DragonFF (https://github.com/Parik27/DragonFF )

You may distribute this program anywhere; please remember to credit the author.
Thank you <3

Program for working with .img .dff .txd files

Functionality:

	.img Batch
		Allows batch rendering of all .dff models from an .img file (or from a pre-extracted folder)
		
	Source Type
	If the 'Batch from IMG' checkbox is enabled, you can select an .img file for further processing.
	If the 'Batch from Folder' checkbox is enabled, instead of an .img file you select a folder where the .img was previously unpacked, or where your desired .dff models and .txd textures are located
	
	Output Image Size
	Enter the vertical image size for each render (default 500px), horizontal size is calculated automatically
	
	Textures
	When the Auto-textures checkbox is active, my experimental texture-matching function will be used to assign textures to objects (works well for clothing models without specified materials, for example).
	If multiple textures are found for a single model - a render will be generated for each texture that the algorithm considers suitable for the model.
		*Function is experimental, unstable, may occasionally select extra textures or fail to find any at all.
			*Searches first by highest material match percentage, then by name match percentage, includes type definitions for certain model categories.

	When the No textures checkbox is active, no textures will be applied to models, they will appear in gray lighting with dim illumination to highlight polygons.
	After selecting | a file/folder |, all .dff files inside | the .img/selected folder | will be displayed in the lower part of the screen
	You can select the ones needed for rendering, or click Select All to choose everything
	Then click 'Batch Render', the rendering process for all images will begin. Real-time progress is displayed in the lower part of the window.
	
	.img unpack
		*allows unpacking, packing, and simply editing .img files
	Unpack IMG
	Select the desired .img, choose a folder where you want to unpack (!!!will automatically create a subfolder in the selected location!!!)
	
	Pack to IMG
	Select a folder containing all the content you want to pack into an .img, then choose where to save the resulting .img
	
	Edit IMG
	Select the desired .img, a separate window opens with all its contents, you can replace .dff and .txd files with ones you need, delete, add new ones. (don't forget to make backups!)
	When pressing save - saves the edited file. Cancel discards changes respectively
	
	Viewer
		*Convenient .img viewer for viewing .dff models
		
     Checkboxes:
  Auto-search textures - uses the same smart texture search algorithm as in .img Batch
  Manual texture selection - allows manually specifying a desired .txd file before selecting a model
  No textures (gray model) - model will be loaded without texture matching
   ***Texture can be added manually while viewing the model
   
	Select a model with the desired texture parameter, enter the Viewer
	
	4 windows open there (Main with the model, and 3 separate windows with HUD elements, can be closed if desired)
	In the Textures window you can enable and disable desired textures, also load more textures with the "Choose More..." button
	In the Geometry window you can hide and show model parts (LOD is disabled by default for vehicles), if a model is identified as clothing, it will split into 3 parts (3 body types)
	In the HUD window current model position, camera zoom, current FPS are displayed
	
The program may be unstable, it has barely been tested.
Thank you :)