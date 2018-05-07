import pandas as pd
import numpy as np

from rpy2.robjects.packages import importr
#get ts object as python object
from rpy2.robjects import pandas2ri
import rpy2.robjects as robjects
ts=robjects.r('ts')
#import forecast package

forecast=importr('forecast')
from dask.distributed import Client, LocalCluster
import dask
from fbprophet import Prophet

class forecast(object):
    
    """
    forecast object used for calling all other functions
    
    Attributes:
        time_series: time series or pandas dataframe to be forecasted
        forecast_periods: num periods to forecast
        frequency: frequency of time series
        confidence_level: confidence level for upper and lower bounds of forecast (optional)
        regressors: boolean check if x regressor will be passed into one of the models
        
    Methods:
        R: wrapper for R_series and R_dataframe
        R_series: function to forecast single time series in R
        R_dataframe: function to forecast multiple time series in R
        prophet: method for forecasting using prophet
        
    Examples:
    
    
    ---------------------------------------------------------------------------------------------------------------------------
        
    

    Notes:
    

    """

    
    def __init__(self,
                 time_series,
                 forecast_periods,
                 frequency,
                 confidence_level=None,
                 regressors=False):
        
        """
        initializes default variables, okay to do like this b/c strings aren't mutable, 
        """
        self.time_series = time_series
        self.forecast_periods = forecast_periods
        self.frequency = frequency
        if confidence_level is None:
            self.confidence_level = 80.0
            
        self.freq_dict = {12:'MS',1:'Y',365:'D',4:'QS',8760:'HS'}
        
        try:
            if regressors:
                self.forecast_type = 0
            #set forecast type to 0 for x regressor series,1 for single series and 2 for dataframe of series
            elif isinstance(self.time_series, pd.core.series.Series):
                self.forecast_type = 1  
            elif isinstance(self.time_series, pd.core.frame.DataFrame):
                self.forecast_type = 2
            else:
                raise TypeError('your forecast object must either be a pandas series or dataframe')
        except TypeError:
            print('your forecast object must either be a pandas series or dataframe')
    
    def R(self,
          model,
          fit_pred=True,
          actual_pred=False,
          pred=False,
          fit=False,
          residuals=False,):
        """wraps R_series and R_dataframe methods to forecast
        forecasting for single series returns a dictionary
        forecasting for dataframe returns back dataframe of predictions
            -can alter parameters to also return fitted values
            
        Args:
            model: pass in R forecast model as string that you want to evaluate, make sure you leave rdata as rdata in all call
            -----Only relevant for dataframes below------
            fit_pred: returns dataframe of fitted and predicted values
            actual_pred: returns dataframe of actual and predicted values
            pred: returns dataframe of predicted values only
            fit: returns dataframe of fitted values only
            residuals: returns dataframe of residual values only

        Returns:
             series: if series passed in, returns dict of parameters of forecast object
             dataframe: if dataframe passed in, dataframe of predictions and optionally fitted values is returned
        
        """
        #this does single series forecast and returns dictionary
        if self.forecast_type == 1:
            return self.R_series(model=model)
        
        if self.forecast_type == 2:
            return self.R_dataframe(model=model,
                                    fit_pred=fit_pred,
                                    actual_pred=actual_pred,
                                    pred=pred,
                                    fit=fit,
                                    residuals=residuals
                                   )

    def R_series(self,
                 model,
                 time_series=None,
                 forecast_periods=None,
                 freq=None,
                 confidence_level=None):
    
        
        """forecasts a time series object using R models in forecast package 
        (https://www.rdocumentation.org/packages/forecast/versions/8.1)
        Note: forecast_ts returns fitted period values as well as forecasted period values
        -Need to make sure forecast function happens in R so dask delayed works correctly
        -This function assumes you have already cleaned time series of nulls and have the time series indexed correctly

        Args:
            time_series: time series object
            model: pass in R forecast model as string that you want to evaluate, make sure you leave rdata as rdata in all calls
            forecast_periods: periods to forecast for
            confidence_level: confidence level for prediction intervals
            freq: frequency of time series (12 is monthly)

        Returns following parameters as a dict:
             model: A list containing information about the fitted model
             method:method name
             predicted:Point forecasts as a time series
             lower: Lower limits for prediction intervals
             upper: Upper limits for prediction intervals
             level: The confidence values associated with the prediction intervals
             x: The original time series
             residuals: Residuals from the fitted model. That is x minus fitted values.
             fitted: Fitted values (one-step forecasts)
             full_fit: fitted + predicted values as one time series
             full_actual: actual + predicted values as one time series

        """
        if time_series is None:
            time_series = self.time_series
        if forecast_periods is None:
            forecast_periods = self.forecast_periods
        if freq is None:
            freq = self.frequency
        if confidence_level is None:
            confidence_level = self.confidence_level
            
        #set frequency string to monthly start if frequency is 12
        freq_string = self.freq_dict[freq]

        #find the start of the time series
        start_ts = time_series[time_series.notna()].index[0]
        #find the end of the time series
        end_ts = time_series[time_series.notna()].index[-1]
        #extract actual time series
        time_series = time_series.loc[start_ts:end_ts]
        #converts to ts object in R
        time_series_R = robjects.IntVector(time_series)
        rdata=ts(time_series_R,frequency=freq)


        #if forecast model ends in f, assume its a direct forecasting object so handle it differently, no need to fit
        if model.split('(')[0][-1] == 'f':
            rstring="""
             function(rdata){
             library(forecast)
             fc<-%s(rdata,h=%s,level=c(%s))
             return(list(model=fc$model, method=fc$method,mean=fc$mean,lower=fc$lower,upper=fc$upper,level=fc$level,x=fc$x,residuals=fc$residuals,fitted=fc$fitted))
             }
            """ % (model,forecast_periods,confidence_level)

        elif model == 'naive' or model == 'snaive':
            rstring="""
             function(rdata){
             library(forecast)
             fc<-%s(rdata,h=%s,level=c(%s))
             return(list(model=fc$model, method=fc$method,mean=fc$mean,lower=fc$lower,upper=fc$upper,level=fc$level,x=fc$x,residuals=fc$residuals,fitted=fc$fitted))
             }
            """ % (model,forecast_periods,confidence_level)


        else:
            rstring="""
             function(rdata){
             library(forecast)
             fitted_model<-%s
             fc<-forecast(fitted_model,h=%s,level=c(%s))
             return(list(model=fc$model, method=fc$method,mean=fc$mean,lower=fc$lower,upper=fc$upper,level=fc$level,x=fc$x,residuals=fc$residuals,fitted=fc$fitted))
             }
            """ % (model,forecast_periods,confidence_level)

        rfunc=robjects.r(rstring)
        #gets fitted and predicted series, and lower and upper prediction intervals from R model
        model,method,mean,lower,upper,level,x,residuals,fitted=rfunc(rdata)
        method=pandas2ri.ri2py(model)
        mean=pandas2ri.ri2py(mean)
        lower=pandas2ri.ri2py(lower).ravel()
        upper=pandas2ri.ri2py(upper).ravel()
        level=pandas2ri.ri2py(level)
        x=pandas2ri.ri2py(x)
        residuals=pandas2ri.ri2py(residuals)
        fitted=pandas2ri.ri2py(fitted)

        #converting predicted numpy array to series, get index for series
        index=pd.date_range(start=time_series.index.max(),periods=len(mean)+1,freq=freq_string)[1:]

        try:
            predicted_series = pd.Series(mean,index=index)
        except:
            #need for splinef because returns array with 2 brackets
            predicted_series = pd.Series(mean.ravel(),index=index)

        #Convert fitted array to series
        fitted_series = pd.Series(fitted,index=pd.date_range(start=time_series[time_series.notnull()].index.min(),periods=len(time_series[time_series.notnull()]),freq=freq_string))
        residual_series = pd.Series(residuals,index=pd.date_range(start=time_series[time_series.notnull()].index.min(),periods=len(time_series[time_series.notnull()]),freq=freq_string))
        #Create full series
        full_fit = fitted_series.append(predicted_series)
        full_actuals = time_series.append(predicted_series)

        #make sure level returned as single int instead of array
        level = int(level[0])

        return {'model':model, 'method':method ,'predicted':predicted_series,'lower':lower,'upper':upper,'level':level,
                'x':time_series,'residuals':residual_series,'fitted':fitted_series,'full_fit':full_fit,'full_actuals':full_actuals}
    
    def R_dataframe(self,
                    model,
                    fit_pred = True,
                    actual_pred=False,
                    pred=False,
                    fit=False,
                    residuals=False,
                    time_series=None):
    
        
        """forecasts a dataframe of time series using model specified
        -Need to make sure forecast function happens in R so dask delayed works correctly
        -This function assumes you have already cleaned time series of nulls and have the time series indexed correctly

        Args:
            model: pass in R forecast model as string that you want to evaluate, make sure you leave rdata as rdata in all calls
            time_series: input dataframe
            ----- only one of below boolean values can be set to true -----
            fit_pred: returns dataframe of fitted and predicted values
            actual_pred: returns dataframe of actual and predicted values
            pred: returns dataframe of predicted values only
            fit: returns dataframe of fitted values only
            residuals: returns dataframe of residual values only

        """
        if time_series is None:
            time_series = self.time_series
            
        output_series = []
        for i in time_series:
            forecasted_dict = dask.delayed(self.R_series)(model,time_series[i])
            #returns correct series object from R_series method based on input param
            if fit_pred:
                forecasted_series = forecasted_dict['full_fit']
            if actual_pred:
                forecasted_series = forecasted_dict['full_actuals']
            if pred:
                forecasted_series = forecasted_dict['predicted']
            if fit:
                forecasted_series = forecasted_dict['fitted']
            if residuals:
                forecasted_series = forecasted_dict['residuals']
                
            output_series.append(forecasted_series)
            
        total = dask.delayed(output_series).compute()
        forecast_df = pd.concat(total,ignore_index=False,keys=time_series.columns,axis=1)
        
        return forecast_df
