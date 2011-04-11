/* 
Copyright (c) 2010. All rights reserved.
LICENSE: NASA Open Source License
*/

var openmdao = (typeof openmdao == "undefined" || !openmdao ) ? {} : openmdao ; 

/**
 * 
 * @version 0.0.0
 * @constructor
 */
openmdao.Model=function() {

    /***********************************************************************
     *  private (available only to privileged methods) 
     ***********************************************************************/
     
    var that = this,
        callbacks = [],
        modelJSON = null,
        types = null
        
    /***********************************************************************
     *  privileged (can access privates, accessible to public and outside) 
     ***********************************************************************/
     
    /** add a listener, i.e. a function that will be called when something changes */
    this.addListener = function(callback) {
        callbacks.push(callback)
    }

    /** notify all listeners that something has changed (by calling all callbacks) */
    this.updateListeners = function() {
        debug.info('Model: updating listeners:')
        for ( var i = 0; i < callbacks.length; i++ )
            if (typeof callbacks[i] == 'function')
                callbacks[i]()
            else
                debug.error('Model: listener did not provide a valid callback function!')
    }

    /** get the list of object types that are available for creation */
    this.getTypes = function(callback, errorHandler) {
        if (typeof callback != 'function')
            return;

        jQuery.ajax({
            url: 'types',
            dataType: 'xml',
            data: {},
            success: function(xml) {
                        types = jQuery("Types",xml)
                        callback(types)
                     },
            error: errorHandler
        })
    }

    /** get a JSON representation of the model */
    this.getJSON = function(callback, errorHandler) {
        if (typeof callback != 'function')
            return
            
        if (modelJSON != null) {
            callback(modelJSON)
        }
        else {
            jQuery.ajax({
                url: 'model.json',
                dataType: 'json',
                data: {},
                success: function(json) {
                            modelJSON = json
                            callback(modelJSON)
                         },
                error: errorHandler
            })
        }
    }
    
    /** get a JSON representation the specified object in the model */
    this.getObject = function(pathname, callback, errorHandler) {
        if (typeof callback != 'function')
            return

        if (modelJSON == null)
            that.getJSON()
            
        var obj = modelJSON

        if (pathname.length >0) {
            var tokens = pathname.split('.'),
                len=tokens.length
            for (i=0;i<len;i++) {
                if (typeof obj[tokens[i]] !== "undefined")
                    obj = obj[tokens[i]]
                else    // may be under py/state
                    obj = obj["py/state"][tokens[i]]
            }
        }
        
        callback(obj)
    }
    
    /** add an object of the specified type & name to the model (at x,y) */
    this.addComponent = function(typepath,name,x,y) {
        // invalidate cached model data
        modelJSON = null
        
        if (typeof(x) !== 'number')  x = 1
        if (typeof(y) !== 'number')  y = 1
        
        jQuery.ajax({
            type: 'POST',
            url:  'add',
            data: {'type': typepath, 'name': name, 'x': x, 'y': y },
            success: that.updateListeners
        })
    }

    /** issue the specified command against the model */
    this.issueCommand = function(cmd, callback, errorHandler) {
        // invalidate cached model data
        modelJSON = null
        
        // make the call
        jQuery.ajax({
            type: 'POST',
            url:  'command',
            data: { 'command': cmd },
            success: function(txt) { 
                        if (typeof callback == 'function') {
                            callback(txt)
                        };
                        that.updateListeners()
                     },
            error: errorHandler
        })
    }

    /** get any queued output from the model */
    this.getOutput = function(callback, errorHandler) {
        jQuery.ajax({
            url: 'output',
            success: function(text) { 
                        if (typeof callback == 'function') {
                            callback(text)
                        };
                     },
            error: errorHandler
        })
    }

    /** set the working directory of the model */
    this.setFolder = function(folder) {
        jQuery.ajax({
            type: 'POST',
            url:  'folder',
            data: { 'folder': folder },
            success: that.updateListeners
        })
    }

    /** get the working directory of the model */
    this.getFolder = function() {
        jQuery.ajax({
            url: 'folder',
            success: function(folder) { return folder }
        })
    }

    /** get a recursize file listing of the model working directory (as JSON) */
    this.getFiles = function(callback, errorHandler) {
        if (typeof callback != 'function')
            return

        jQuery.ajax({
            url: 'files.json',
            dataType: 'json',
            data: {},
            success: callback,
            error: errorHandler
        })
    }

    /** get the contents of the specified file */
    this.getFile = function(filepath, callback, errorHandler) {
        if (typeof callback != 'function')
            return;

        jQuery.ajax({
            url: 'file',
            type: 'GET',
            dataType: 'text',
            data: { 'file': filepath },
            success: callback,
            error: errorHandler
        })
    }

    /** set the contents of the specified file */
    this.setFile = function(filepath, contents, errorHandler) {
        jQuery.ajax({
            url: 'file',
            type: 'POST',
            data: { 'filename': filepath, 'contents': contents},
            success: that.updateListeners,
            error: errorHandler
        })
    }

    /** create a new folder in the model working directory with the specified path */
    this.createFolder = function(folderpath) {
        jQuery.ajax({
            url: 'file',
            type: 'POST',
            data: { 'filename': folderpath, 'isFolder': true},
            success: that.updateListeners
        })
    }

    /** create a new file in the model working directory with the specified path  */
    this.newFile = function(folderpath) {
        openmdao.Util.promptForName(function(name) {
            if (folderpath)
                name = folderpath+'/'+name
            var contents = '"""\n   '+name+'\n"""\n\n'
            that.setFile(name,contents)
        })
    }

    /** prompt for name & create a new folder */
    this.newFolder = function(folderpath) {
        openmdao.Util.promptForName(function(name) {
            if (folderpath)
                name = folderpath+'/'+name
            that.createFolder(name,that.updateListeners)
        })
    }

    /** upload a file to the model working directory */
    this.uploadFile = function() {
        // TODO: make this an AJAX call so we can updateListeners afterwards
        openmdao.Util.popupWindow('/upload','Add File',150,400);
    }

    /** delete the file in the model working directory with the specified path */
    this.removeFile = function(filepath) {
        jQuery.ajax({
            url: 'remove',
            type: 'POST',
            dataType: 'text',
            data: { 'file': filepath },
            success: that.updateListeners
        })
    }
    
    /** import the contents of the specified file into the model */
    this.importFile = function(filepath) {
        // change path to package notation and import
        var path = filepath.replace(/.py/g,'').
                            replace(/\\/g,'.').
                            replace(/\//g,'.')
        that.issueCommand("from "+path+" import *")
        that.updateListeners
    }

    /** execute the specified file */
    this.execFile = function(filepath) {
        // invalidate cached model data
        modelJSON = null

        // convert to relative path with forward slashes
        var path = filepath.replace(/\\/g,'/')
        if (path[0] == '/')
            path = path.substring(1,path.length)

        // make the call
        jQuery.ajax({
            url: 'exec',
            type: 'POST',
            data: { 'filename': path },
            success: that.updateListeners
        })
    }

    /** exit the model */
    this.exit = function() {
        jQuery.ajax({
            url: 'exit',
            type: 'GET',
        })
    }
    
}



