import wx
from subsync.gui.downloadwin import DownloadWin
from subsync.gui.busydlg import BusyDlg
from subsync.gui.components import popups
from subsync.assets import assetManager
from subsync.data import descriptions
from subsync.settings import settings
from subsync.error import Error
from subsync.synchro import transcribe
from subsync import utils
import threading


def validateAssets(parent, tasks, updateAssets=True, askForLang=True, autoSave=False):
    if askForLang and settings().showLanguageNotSelectedPopup:
        if not askForLangSelection(parent, tasks):
            return False

    assets = assetManager().getAssetsForTasks(tasks)

    if assets.notInstalled():
        updateAssetList(parent)

    assets.validate()

    if assets.notInstalled():
        if not askForDownloadAssets(parent, assets.notInstalled()):
            return False

    if updateAssets and assets.hasUpdate():
        askForUpdateAssets(parent, assets.hasUpdate())

    if needsSpeechModel(tasks) and transcribe.isModelInstalled() is False:
        if not askForDownloadSpeechModel(parent):
            return False

    return True

def needsSpeechModel(tasks):
    return any(task.ref and task.ref.type == 'audio' and transcribe.supports(task.ref.lang)
            for task in tasks)

def askForDownloadSpeechModel(parent):
    size = transcribe.getModelSize()
    msg  = [ _('Speech in this language is recognized with the Whisper speech recognition model.') ]
    if size:
        msg += [ _('It must be downloaded once ({}) and is kept for later use.').format(utils.fileSizeFmt(size)) ]
    msg += [ '', _('Download now?') ]
    title = _('Download speech recognition model')
    flags = wx.YES_NO | wx.ICON_QUESTION
    with wx.MessageDialog(parent, '\n'.join(msg), title, flags) as dlg:
        if dlg.ShowModal() == wx.ID_YES:
            return downloadSpeechModel(parent)
    return False

def downloadSpeechModel(parent):
    state = { 'pos': 0, 'size': transcribe.getModelSize(), 'done': False,
            'error': None, 'cancel': False }

    def onProgress(pos, size):
        state['pos'], state['size'] = pos, size

    def run():
        try:
            state['done'] = transcribe.downloadModel(
                    runCb=lambda: not state['cancel'], progressCb=onProgress)
        except Exception as err:
            state['error'] = err

    thread = threading.Thread(target=run, name='ModelDownload', daemon=True)
    thread.start()

    title = _('Download speech recognition model')
    style = wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME
    dlg = wx.ProgressDialog(title, _('Downloading...') + ' ' * 40, maximum=1000,
            parent=parent, style=style)
    try:
        while thread.is_alive():
            pos, size = state['pos'], state['size']
            msg = _('Downloading...') + ' ' + utils.fileSizeFmt(pos)
            if size:
                msg += ' / ' + utils.fileSizeFmt(size)
                cont, _skip = dlg.Update(min(int(1000 * pos / size), 999), msg)
            else:
                cont = dlg.Pulse(msg)[0]
            if not cont:
                state['cancel'] = True
                break
            wx.MilliSleep(200)
    finally:
        dlg.Destroy()

    thread.join()
    if state['error'] is not None:
        raise Error(_("Couldn't download the speech recognition model, "
                "check your internet connection")).add('details', str(state['error']))
    return state['done']

def updateAssetList(parent):
    listUpdater = assetManager().getAssetListUpdater()
    if not listUpdater.isRunning() and not listUpdater.isUpdated():
        listUpdater.run()

    if listUpdater.isRunning():
        with BusyDlg(parent, _('Downloading assets list...')) as dlg:
            dlg.ShowModalWhile(listUpdater.isRunning)

    return listUpdater.isUpdated()

def askForDownloadAssets(parent, assetList):
    msg  = [ _('Following assets must be download to continue:') ]
    msg += [ ' - ' + asset.getPrettyName() for asset in assetList ]
    msg += [ '', _('Download now?') ]
    title = _('Download assets')
    flags = wx.YES_NO | wx.ICON_QUESTION
    with wx.MessageDialog(parent, '\n'.join(msg), title, flags) as dlg:
        if dlg.ShowModal() == wx.ID_YES:
            return downloadAssets(parent, assetList)
    return False

def askForUpdateAssets(parent, assetList):
    msg  = [ _('Following assets could be updated:') ]
    msg += [ ' - ' + asset.getPrettyName() for asset in assetList ]
    msg += [ '', _('Update now?') ]
    title = _('Update assets')
    flags = wx.YES_NO | wx.ICON_QUESTION
    with wx.MessageDialog(parent, '\n'.join(msg), title, flags) as dlg:
        if dlg.ShowModal() == wx.ID_YES:
            return downloadAssets(parent, assetList)
    return False

def downloadAssets(parent, assetList):
    for asset in assetList:
        with DownloadWin(parent, asset) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return False
    return True

def askForLangSelection(parent, tasks):
    msg = [ _('No language selected for:') ]
    missingLang = False
    for task in tasks:
        if not task.sub.lang:
            msg.append(_('subtitles: ') + task.sub.path)
            missingLang = True
        if not task.ref.lang:
            msg.append(_('references: ') + task.ref.path)
            missingLang = True

    if missingLang:
        msg += [ '', descriptions.noLanguageSelectedQuestion ]
        title = _('No language selected')
        return popups.showConfirmationPopup(parent, '\n'.join(msg), title,
                confirmKey='showLanguageNotSelectedPopup')

    return True
