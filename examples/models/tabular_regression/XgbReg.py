import xgboost as xgb
from sklearn.metrics import mean_squared_error
from collections import OrderedDict
import pickle
import base64
import numpy as np
import pandas as pd

from pathlib import Path
import sys
import os

from rafiki.model import BaseModel, InvalidModelParamsException, test_model_class, \
                        IntegerKnob, FloatKnob, logger
from rafiki.constants import TaskType, ModelDependency

class XgbReg(BaseModel):
    '''
    Implements a XGBoost Regressor for tabular data regression task
    '''
    @staticmethod
    def get_knob_config():
        return {
            'n_estimators': IntegerKnob(50, 200),
            'min_child_weight': IntegerKnob(1, 6),
            'max_depth': IntegerKnob(1, 10),
            'gamma': FloatKnob(0.0, 1.0, is_exp=False),
            'subsample': FloatKnob(0.5, 1.0, is_exp=False),
            'colsample_bytree': FloatKnob(0.1, 0.7, is_exp=False)
        }

    def __init__(self, **knobs):
        self.__dict__.update(knobs)
        self._clf = self._build_classifier(self.n_estimators, self.min_child_weight, \
            self.max_depth, self.gamma, self.subsample, self.colsample_bytree)
       
    def train(self, dataset_path, features=None, target=None):
        # Record features & target
        self._features = features
        self._target = target
        
        # Load CSV file as pandas dataframe
        csv_path = dataset_path
        data = pd.read_csv(csv_path)

        # Extract X & y from dataframe
        (X, y) = self._extract_xy(data)

        # Encode categorical features
        X = self._encoding_categorical_type(X)

        self._clf.fit(X, y)

        # Compute train root mean square error
        preds = self._clf.predict(X)
        rmse = np.sqrt(mean_squared_error(y, preds))
        logger.log('Train RMSE: {}'.format(rmse))

    def evaluate(self, dataset_path):
        # Load CSV file as pandas dataframe
        csv_path = dataset_path
        data = pd.read_csv(csv_path)

        # Extract X & y from dataframe
        (X, y) = self._extract_xy(data)

        # Encode categorical features
        X = self._encoding_categorical_type(X)

        preds = self._clf.predict(X)
        rmse = np.sqrt(mean_squared_error(y, preds))
        return rmse

    def predict(self, queries):
        queries = [pd.DataFrame(query, index=[0]) for query in queries]
        results = [self._clf.predict(self._features_mapping(query)).tolist()[0] for query in queries]
        return results

    def destroy(self):
        pass

    def dump_parameters(self):
        params = {}

        # Put model parameters
        clf_bytes = pickle.dumps(self._clf)
        clf_base64 = base64.b64encode(clf_bytes).decode('utf-8')
        params['clf_base64'] = clf_base64
        params['encoding_dict'] = self._encoding_dict

        return params

    def load_parameters(self, params):
        # Load model parameters
        clf_base64 = params['clf_base64']
        if clf_base64 is None:
            raise InvalidModelParamsException()
        clf_bytes = base64.b64decode(clf_base64.encode('utf-8'))
        self._clf = pickle.loads(clf_bytes)
        self._encoding_dict = params['encoding_dict']

    def _extract_xy(self, data):
        features = self._features
        target = self._target

        if features is None:
            X = data.iloc[:,:-1]
        else:
            X = data[features]
            
        if target is None:
            y = data.iloc[:,-1]
        else:
            y = data[target]

        return (X, y)
        
    def _encoding_categorical_type(self, cols):
        # Apply label encoding for those categorical columns
        cat_cols = list(filter(lambda x: cols[x].dtype == 'object', cols.columns))
        encoded_cols = pd.DataFrame({col: cols[col].astype('category').cat.codes \
            if cols[col].dtype == 'object' else cols[col] for col in cols}, index=cols.index)

        # Recover the missing elements (Use XGBoost to automatically handle them)
        encoded_cols = encoded_cols.replace(to_replace = -1, value = np.nan)

        # Generate the dict that maps categorical features to numerical
        encoding_dict = {col: {cat: n for n, cat in enumerate(cols[col].astype('category'). \
            cat.categories)} for col in cat_cols}
        self._encoding_dict = encoding_dict

        return encoded_cols

    def _features_mapping(self, df):
        # Encode the categorical features with pre saved encoding dict
        cat_cols = list(filter(lambda x: df[x].dtype == 'object', df.columns))
        df_temp = df.copy()
        for col in cat_cols:
            df_temp[col] = df[col].map(self._encoding_dict[col])
        df = df_temp
        return df

    def _build_classifier(self, n_estimators, min_child_weight, max_depth, gamma, subsample, colsample_bytree):
        clf = xgb.XGBRegressor(
            n_estimators=n_estimators,
            min_child_weight=min_child_weight,
            max_depth=max_depth,
            gamma=gamma,
            subsample=subsample,
            colsample_bytree=colsample_bytree
        ) 
        return clf

if __name__ == '__main__':
    test_model_class(
        model_file_path=__file__,
        model_class='XgbReg',
        task=TaskType.TABULAR_REGRESSION,
        dependencies={
            ModelDependency.XGBOOST: '0.90'
        },
        train_dataset_path='data/bodyfat_train.csv',
        val_dataset_path='data/bodyfat_val.csv',
        train_args={
            'features': ['density',
                        'age',
                        'weight',
                        'height',
                        'neck',
                        'chest',
                        'abdomen',
                        'hip',
                        'thigh',
                        'knee',
                        'ankle',
                        'biceps',
                        'forearm',
                        'wrist'],
            'target': 'bodyfat'
        },
        queries=[
             {'density': 1.0207,
             'age': 65,
             'weight': 224.5,
             'height': 68.25,
             'neck': 38.8,
             'chest': 119.6,
             'abdomen': 118.0,
             'hip': 114.3,
             'thigh': 61.3,
             'knee': 42.1,
             'ankle': 23.4,
             'biceps': 34.9,
             'forearm': 30.1,
             'wrist': 19.4}
        ]
    )
